"""Semantic model evaluation, export, and ad-hoc validation operations.

This service provides the Day 7 model lifecycle operations (evaluate, export,
test-predict) adapted for the LoveDA semantic segmentation workflow.  Training
still happens offline in ``training/loveda_semantic``; this module consumes the
artifacts produced by that training pipeline.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageOps
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.exceptions import DomainError
from app.core.logger import get_logger
from app.entity.db_models import DetectionScene, ModelVersion
from app.services.semantic_inference import build_artifacts, preprocess
from app.storage.minio_client import MinIOClient

logger = get_logger(__name__)

# LoveDA semantic segmentation constants (mirrored from training/loveda_semantic/common.py)
CLASS_NAMES = ("background", "building", "road", "water", "barren", "forest", "agricultural")
DISPLAY_NAMES = {
    "background": "背景",
    "building": "建筑",
    "road": "道路",
    "water": "水体",
    "barren": "裸地",
    "forest": "森林",
    "agricultural": "农田",
}
PALETTE = np.asarray(
    [
        (0, 0, 0),
        (255, 64, 64),
        (255, 200, 64),
        (64, 160, 255),
        (180, 120, 64),
        (64, 180, 96),
        (180, 220, 64),
    ],
    dtype=np.uint8,
)
IGNORE_COLOR = np.asarray((160, 160, 160), dtype=np.uint8)
NC = 7
IGNORE = 255
IMGSZ = 512


def _training_root() -> Path:
    """Return the absolute training/loveda_semantic directory."""
    return (Path(__file__).resolve().parents[3] / "training" / "loveda_semantic").resolve()


def _default_artifact_dir() -> Path:
    """Return the baseline artifact directory (parent of deploy/)."""
    return settings.semantic_deploy_path.resolve().parent


def _default_run_dir() -> Path:
    """Return the configured training run directory, if any."""
    run = _training_root() / settings.MODEL_MANAGEMENT_TRAINING_RUN_DIR
    if run.is_dir():
        return run.resolve()
    return _training_root() / "runs" / "baseline_e50_i512_b2"


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_cached_metrics(*candidate_dirs: Path) -> dict[str, Any] | None:
    """Load a previously saved metrics.json report from candidate directories."""
    for directory in candidate_dirs:
        path = directory / "metrics.json"
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
    return None


def _confusion_update(matrix: np.ndarray, target: np.ndarray, prediction: np.ndarray) -> tuple[int, int]:
    """Update a confusion matrix with one image pair, collapsing internal label 7 to 0."""
    valid = target != IGNORE
    target = target[valid].astype(np.int64)
    prediction = prediction[valid].astype(np.int64)
    prediction[prediction == NC] = 0
    if np.any((target < 0) | (target >= NC)) or np.any((prediction < 0) | (prediction >= NC)):
        raise ValueError("Label outside the public 0..6 range after ignore filtering/remapping")
    matrix += np.bincount(NC * target + prediction, minlength=NC * NC).reshape(NC, NC)
    return int(valid.sum()), int((~valid).sum())


def _metrics_from_matrix(matrix: np.ndarray) -> dict[str, Any]:
    """Compute mIoU, pixel accuracy, Dice/F1 and per-class metrics from a confusion matrix."""
    matrix = matrix.astype(np.float64)
    tp = np.diag(matrix)
    gt = matrix.sum(axis=1)
    predicted = matrix.sum(axis=0)
    union = gt + predicted - tp
    iou = np.divide(tp, union, out=np.full(NC, np.nan), where=union > 0)
    dice = np.divide(2 * tp, gt + predicted, out=np.full(NC, np.nan), where=(gt + predicted) > 0)
    precision = np.divide(tp, predicted, out=np.full(NC, np.nan), where=predicted > 0)
    recall = np.divide(tp, gt, out=np.full(NC, np.nan), where=gt > 0)
    total = matrix.sum()
    return {
        "miou": float(np.nanmean(iou)),
        "pixel_accuracy": float(tp.sum() / total) if total else None,
        "mean_dice_f1": float(np.nanmean(dice)),
        "valid_pixels": int(total),
        "per_class": [
            {
                "class_id": i,
                "class_name": CLASS_NAMES[i],
                "display_name": DISPLAY_NAMES[CLASS_NAMES[i]],
                "iou": iou[i],
                "dice_f1": dice[i],
                "precision": precision[i],
                "recall": recall[i],
                "support_pixels": int(gt[i]),
            }
            for i in range(NC)
        ],
        "confusion_matrix": matrix.astype(np.int64),
    }


def _colorize(mask: np.ndarray, ignored: np.ndarray | None = None) -> np.ndarray:
    safe = mask.copy()
    safe[safe >= NC] = 0
    rgb = PALETTE[safe]
    if ignored is not None:
        rgb[ignored] = IGNORE_COLOR
    return rgb


def _save_confusion_plot(matrix: np.ndarray, output: Path, normalized: bool = False) -> None:
    """Render a confusion matrix image using matplotlib."""
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        logger.warning("matplotlib not available, skipping confusion matrix plot: %s", exc)
        return

    values = matrix.astype(float)
    if normalized:
        values = np.divide(
            values,
            values.sum(1, keepdims=True),
            out=np.zeros_like(values),
            where=values.sum(1, keepdims=True) > 0,
        )
    fig, ax = plt.subplots(figsize=(9, 8))
    image = ax.imshow(values, cmap="Blues")
    fig.colorbar(image, ax=ax)
    ax.set(
        xticks=range(NC),
        yticks=range(NC),
        xticklabels=CLASS_NAMES,
        yticklabels=CLASS_NAMES,
        xlabel="Predicted",
        ylabel="Ground truth",
        title="Pixel Confusion Matrix" + (" (row normalized)" if normalized else ""),
    )
    plt.setp(ax.get_xticklabels(), rotation=35, ha="right")
    threshold = values.max() * 0.55 if values.size else 0
    for row in range(NC):
        for col in range(NC):
            text = f"{values[row, col]:.3f}" if normalized else f"{int(values[row, col]):,}"
            ax.text(
                col,
                row,
                text,
                ha="center",
                va="center",
                fontsize=7,
                color="white" if values[row, col] > threshold else "black",
            )
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def _save_per_class_iou_plot(report: dict[str, Any], output: Path) -> None:
    """Render a per-class IoU comparison bar chart."""
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        logger.warning("matplotlib not available, skipping per-class IoU plot: %s", exc)
        return

    x = np.arange(NC)
    width = 0.25
    fig, ax = plt.subplots(figsize=(11, 6))
    for offset, domain in enumerate(("overall", "Urban", "Rural")):
        ax.bar(
            x + (offset - 1) * width,
            [row["iou"] for row in report[domain]["per_class"]],
            width,
            label=domain,
        )
    ax.set(xticks=x, xticklabels=CLASS_NAMES, ylim=(0, 1), ylabel="IoU", title="Per-class IoU by domain")
    ax.legend()
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def _write_evaluation_artifacts(report: dict[str, Any], artifact_dir: Path) -> None:
    """Persist evaluation report, CSV summaries and plots under artifact_dir."""
    artifact_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = artifact_dir / "metrics.json"
    metrics_path.write_text(
        json.dumps(report, default=_jsonable, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    # Keep the packaged deploy copy in sync so downstream consumers still find it.
    deploy_metrics = artifact_dir / "deploy" / "metrics.json"
    if deploy_metrics.parent.is_dir():
        shutil.copy2(metrics_path, deploy_metrics)
    with (artifact_dir / "metrics_summary.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["domain", "images", "valid_pixels", "ignored_pixels", "miou", "pixel_accuracy", "mean_dice_f1"],
        )
        writer.writeheader()
        for domain, item in report.items():
            writer.writerow({"domain": domain, **{key: item[key] for key in writer.fieldnames if key != "domain"}})
    with (artifact_dir / "per_class_metrics.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields = ["domain", "class_id", "class_name", "iou", "dice_f1", "precision", "recall", "support_pixels"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for domain, item in report.items():
            for row in item["per_class"]:
                writer.writerow({"domain": domain, **row})
    with (artifact_dir / "confusion_matrix.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ground_truth\\prediction", *CLASS_NAMES])
        for name, row in zip(CLASS_NAMES, report["overall"]["confusion_matrix"]):
            writer.writerow([name, *row])
    matrix = np.asarray(report["overall"]["confusion_matrix"])
    _save_confusion_plot(matrix, artifact_dir / "confusion_matrix.png")
    _save_confusion_plot(matrix, artifact_dir / "confusion_matrix_normalized.png", normalized=True)
    _save_per_class_iou_plot(report, artifact_dir / "per_class_iou_by_domain.png")


def _run_pt_evaluation(weights_path: Path, data_root: Path, device: str = "cpu") -> dict[str, Any]:
    """Run full LoveDA validation evaluation using a PyTorch checkpoint."""
    from ultralytics import YOLO

    matrices = {
        "overall": np.zeros((NC, NC), dtype=np.int64),
        "Urban": np.zeros((NC, NC), dtype=np.int64),
        "Rural": np.zeros((NC, NC), dtype=np.int64),
    }
    counts = {key: {"images": 0, "ignored_pixels": 0} for key in matrices}
    sample_dir = _default_artifact_dir().parent / "sample_predictions"
    sample_dir.mkdir(parents=True, exist_ok=True)

    model = YOLO(str(weights_path))
    for region in ("Urban", "Rural"):
        images = sorted((data_root / "images" / "val" / region).glob("*.png"))
        if not images:
            raise FileNotFoundError(f"No validation images for {region} in {data_root}")
        sample_indices = set(np.linspace(0, len(images) - 1, min(4, len(images)), dtype=int).tolist())
        stream = model.predict(
            source=[str(path) for path in images],
            imgsz=IMGSZ,
            batch=2,
            device=device,
            workers=0,
            verbose=False,
            stream=True,
        )
        for index, (path, result) in enumerate(zip(images, stream)):
            mask_path = data_root / "masks" / "val" / region / path.name
            target = cv2.imread(str(mask_path), cv2.IMREAD_UNCHANGED)
            if target is None:
                raise FileNotFoundError(mask_path)
            if target.ndim == 3:
                if target.shape[2] == 1:
                    target = target[..., 0]
                elif target.shape[2] >= 3:
                    if not np.all(target[..., 0] == target[..., 1]) or not np.all(target[..., 0] == target[..., 2]):
                        raise ValueError(f"Mask is not grayscale: {mask_path}")
                    target = target[..., 0]
                else:
                    raise ValueError(f"Unexpected mask shape: {mask_path}: {target.shape}")
            prediction = np.squeeze(result.semantic_mask.data.detach().cpu().numpy()).astype(np.uint8)
            if prediction.ndim != 2:
                raise ValueError(f"Unexpected semantic prediction shape for {path}: {prediction.shape}")
            if prediction.shape != target.shape:
                prediction = cv2.resize(prediction, (target.shape[1], target.shape[0]), interpolation=cv2.INTER_NEAREST)
            valid, ignored = _confusion_update(matrices[region], target, prediction)
            _confusion_update(matrices["overall"], target, prediction)
            for key in (region, "overall"):
                counts[key]["images"] += 1
                counts[key]["ignored_pixels"] += ignored
            if index in sample_indices:
                image = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
                shown_pred = prediction.copy()
                shown_pred[shown_pred == NC] = 0
                panel = np.concatenate(
                    (image, _colorize(target, target == IGNORE), _colorize(shown_pred)),
                    axis=1,
                )
                cv2.imwrite(
                    str(sample_dir / f"{region}_{path.stem}_image_gt_pred.png"),
                    cv2.cvtColor(panel, cv2.COLOR_RGB2BGR),
                )

    report: dict[str, Any] = {}
    for domain, matrix in matrices.items():
        report[domain] = _metrics_from_matrix(matrix)
        report[domain].update(counts[domain])
    return report


class SemanticModelOpsService:
    """Day 7 model lifecycle operations for the LoveDA semantic workflow."""

    def __init__(self) -> None:
        self.artifact_dir = _default_artifact_dir()
        self.deploy_dir = self.artifact_dir / "deploy"
        self.run_dir = _default_run_dir()
        self.models_dir = Path(__file__).resolve().parents[3] / "models" / "semantic"

    def _weights_path(self) -> Path | None:
        """Locate the best PyTorch checkpoint."""
        candidates = [
            self.deploy_dir / "best.pt",
            self.run_dir / "weights" / "best.pt",
        ]
        for path in candidates:
            if path.is_file():
                return path
        return None

    def _onnx_path(self) -> Path | None:
        path = self.deploy_dir / "best_dynamic.onnx"
        return path if path.is_file() else None

    def _data_root(self) -> Path | None:
        """Locate the LoveDA YOLO-formatted data root."""
        candidates = [
            _training_root() / "data" / "loveda_yolo_semantic",
            Path("/data/loveda_yolo_semantic"),
        ]
        for path in candidates:
            if path.is_dir() and (path / "images" / "val").is_dir():
                return path
        return None

    def evaluate(self, device: str = "cpu", force: bool = False) -> dict[str, Any]:
        """Return evaluation metrics, running full validation if needed and allowed."""
        cached = _load_cached_metrics(self.artifact_dir, self.deploy_dir)
        if cached and not force:
            logger.info("Returning cached semantic evaluation metrics")
            return {"source": "cached", "report": cached}

        weights = self._weights_path()
        if weights is None:
            if cached:
                return {"source": "cached", "report": cached, "warning": "模型权重不存在，返回缓存指标"}
            raise DomainError(404, "MODEL_NOT_FOUND", "未找到语义分割模型权重")

        data_root = self._data_root()
        if data_root is None:
            if cached:
                return {"source": "cached", "report": cached, "warning": "验证数据集不存在，返回缓存指标"}
            raise DomainError(404, "DATASET_NOT_FOUND", "未找到 LoveDA 验证数据集")

        logger.info("Running semantic evaluation: weights=%s data=%s", weights, data_root)
        start = time.perf_counter()
        report = _run_pt_evaluation(weights, data_root, device=device)
        elapsed = time.perf_counter() - start
        _write_evaluation_artifacts(report, self.artifact_dir)
        logger.info("Semantic evaluation finished in %.1fs", elapsed)
        return {"source": "evaluated", "report": report, "elapsed_seconds": elapsed}

    def export(
        self,
        db: Session,
        version: str | None = None,
        description: str | None = None,
        set_default: bool = False,
        upload_minio: bool = True,
    ) -> dict[str, Any]:
        """Register the current semantic artifact as a ModelVersion and optionally upload to MinIO."""
        metadata_path = self.deploy_dir / "metadata.json"
        if not metadata_path.is_file():
            raise DomainError(404, "ARTIFACT_NOT_FOUND", "部署产物 metadata.json 不存在")

        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DomainError(500, "ARTIFACT_INVALID", "metadata.json 解析失败") from exc

        metrics = _load_cached_metrics(self.artifact_dir, self.deploy_dir) or {}
        overall = metrics.get("overall", {})

        scene = db.query(DetectionScene).filter(DetectionScene.name == "loveda_semantic").first()
        if scene is None:
            scene = DetectionScene(
                name="loveda_semantic",
                display_name="LoveDA 语义分割",
                description="LoveDA 7 类土地覆盖语义分割",
                category="semantic_segmentation",
                class_names=list(CLASS_NAMES),
                class_names_cn=DISPLAY_NAMES,
            )
            db.add(scene)
            db.commit()
            db.refresh(scene)

        if not version:
            existing_count = (
                db.query(ModelVersion)
                .filter(ModelVersion.scene_id == scene.id, ModelVersion.task_kind == "semantic_segmentation")
                .count()
            )
            version = f"v{existing_count + 1}.0.0"

        export_dir = self.models_dir / f"loveda_semantic_{version}"
        export_dir.mkdir(parents=True, exist_ok=True)

        weights = self._weights_path()
        exported_weight = export_dir / "best.pt"
        if weights is not None:
            shutil.copy2(weights, exported_weight)
        else:
            logger.warning("No best.pt found during export; model version will have no local weight copy")

        onnx = self._onnx_path()
        exported_onnx = None
        if onnx is not None:
            exported_onnx = export_dir / "best_dynamic.onnx"
            shutil.copy2(onnx, exported_onnx)

        # Copy evaluation artifacts into the versioned export directory.
        for name in ("metrics.json", "confusion_matrix.png", "confusion_matrix_normalized.png", "per_class_iou_by_domain.png"):
            src = self.artifact_dir / name
            if src.is_file():
                shutil.copy2(src, export_dir / name)

        minio_url = None
        if upload_minio and weights is not None:
            try:
                client = MinIOClient()
                object_name = f"models/semantic/loveda_semantic/{version}/best.pt"
                minio_url = client.upload_file(object_name, str(exported_weight), content_type="application/octet-stream")
                logger.info("Uploaded semantic model to MinIO: %s", minio_url)
            except Exception as exc:
                logger.warning("MinIO upload failed (export continues): %s", exc)

        per_class = overall.get("per_class", [])
        model_version = ModelVersion(
            scene_id=scene.id,
            training_task_id=None,
            version=version,
            model_name=f"loveda_semantic_{version}",
            model_type=metadata.get("model", "YOLO26n Semantic"),
            status="active",
            model_path=str(exported_weight) if exported_weight.is_file() else str(self.deploy_dir / "best.pt"),
            minio_url=minio_url,
            map50=None,
            map50_95=None,
            precision=None,
            recall=None,
            per_class_ap={row["class_name"]: row["iou"] for row in per_class},
            description=description or f"LoveDA 语义分割模型导出 {version}",
            file_size=exported_weight.stat().st_size if exported_weight.is_file() else None,
            is_default=False,
            task_kind="semantic_segmentation",
            runtime="onnx",
            artifact_sha256=_sha256_file(exported_weight) if exported_weight.is_file() else None,
            model_metadata={
                "source_artifact_dir": str(self.artifact_dir),
                "deploy_dir": str(self.deploy_dir),
                "metadata": metadata,
                "onnx_exported": exported_onnx is not None and exported_onnx.is_file(),
                "exported_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        db.add(model_version)

        if set_default:
            db.query(ModelVersion).filter(
                ModelVersion.scene_id == scene.id,
                ModelVersion.task_kind == "semantic_segmentation",
                ModelVersion.id != model_version.id,
            ).update({"is_default": False})
            model_version.is_default = True

        db.commit()
        db.refresh(model_version)

        logger.info(
            "Semantic model exported: version=%s scene_id=%s default=%s",
            version,
            scene.id,
            set_default,
        )
        return {
            "model_version_id": model_version.id,
            "version": version,
            "scene_id": scene.id,
            "model_name": model_version.model_name,
            "model_path": model_version.model_path,
            "export_dir": str(export_dir),
            "minio_url": minio_url,
            "file_size": model_version.file_size,
            "is_default": model_version.is_default,
            "evaluation": {
                "miou": overall.get("miou"),
                "pixel_accuracy": overall.get("pixel_accuracy"),
                "mean_dice_f1": overall.get("mean_dice_f1"),
                "per_class": per_class,
            },
            "message": f"模型已导出为版本 {version}",
        }

    def list_versions(self, db: Session) -> list[dict[str, Any]]:
        """List all registered semantic segmentation model versions."""
        items = (
            db.query(ModelVersion)
            .filter(ModelVersion.task_kind == "semantic_segmentation")
            .order_by(ModelVersion.created_at.desc())
            .all()
        )
        return [
            {
                "id": item.id,
                "version": item.version,
                "model_name": item.model_name,
                "model_type": item.model_type,
                "model_path": item.model_path,
                "runtime": item.runtime,
                "artifact_sha256": item.artifact_sha256,
                "task_kind": item.task_kind,
                "is_default": item.is_default,
                "status": item.status,
                "map50": item.map50,
                "map50_95": item.map50_95,
                "precision": item.precision,
                "recall": item.recall,
                "per_class_ap": item.per_class_ap,
                "file_size": item.file_size,
                "minio_url": item.minio_url,
                "description": item.description,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in items
        ]

    def get_download_path(self, version_id: int, db: Session) -> dict[str, Any]:
        """Return the local path and filename for a ModelVersion download."""
        model = (
            db.query(ModelVersion)
            .filter(ModelVersion.id == version_id, ModelVersion.task_kind == "semantic_segmentation")
            .first()
        )
        if not model:
            raise DomainError(404, "MODEL_VERSION_NOT_FOUND", "模型版本不存在")
        path = Path(model.model_path)
        if not path.is_file():
            raise DomainError(404, "MODEL_FILE_NOT_FOUND", "模型文件不存在")
        return {"file_path": str(path), "filename": f"{model.model_name}.pt"}

    def predict(self, image: Image.Image, use_pt_fallback: bool = True) -> dict[str, Any]:
        """Run ad-hoc semantic inference on one image and return a base64 annotated result."""
        onnx_path = self._onnx_path()
        if onnx_path is not None:
            return self._predict_onnx(image)
        if use_pt_fallback:
            weights = self._weights_path()
            if weights is not None:
                return self._predict_pt(image, weights)
        raise DomainError(503, "MODEL_UNAVAILABLE", "没有可用的语义分割推理模型（缺少 ONNX 或 PT 权重）")

    def _predict_onnx(self, image: Image.Image) -> dict[str, Any]:
        import onnxruntime as ort

        onnx_path = self._onnx_path()
        metadata_path = self.deploy_dir / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        classes = metadata["classes"]

        session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
        input_name = session.get_inputs()[0].name
        output_name = session.get_outputs()[0].name

        original = ImageOps.exif_transpose(image).convert("RGB")
        tensor = preprocess(original, (IMGSZ, IMGSZ))
        started = time.perf_counter()
        output = session.run([output_name], {input_name: tensor})[0]
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        artifacts = build_artifacts(original, output, classes, settings.SEMANTIC_OVERLAY_ALPHA)

        annotated_image = base64.b64encode(artifacts.overlay).decode("utf-8")
        return {
            "total_objects": None,  # semantic segmentation uses pixel stats instead
            "class_statistics": artifacts.class_statistics,
            "annotated_image": annotated_image,
            "inference_time_ms": elapsed,
            "model": metadata.get("model"),
        }

    def _predict_pt(self, image: Image.Image, weights_path: Path) -> dict[str, Any]:
        from ultralytics import YOLO

        original = ImageOps.exif_transpose(image).convert("RGB")
        model = YOLO(str(weights_path))
        results = model.predict(source=np.asarray(original), imgsz=IMGSZ, device="cpu", verbose=False)
        result = results[0]
        prediction = np.squeeze(result.semantic_mask.data.detach().cpu().numpy()).astype(np.uint8)

        # Build a fake output array that matches the ONNX contract for build_artifacts.
        output = prediction[None, ...]
        metadata_path = self.deploy_dir / "metadata.json"
        classes = json.loads(metadata_path.read_text(encoding="utf-8"))["classes"]
        artifacts = build_artifacts(original, output, classes, settings.SEMANTIC_OVERLAY_ALPHA)

        annotated_image = base64.b64encode(artifacts.overlay).decode("utf-8")
        return {
            "total_objects": None,
            "class_statistics": artifacts.class_statistics,
            "annotated_image": annotated_image,
            "inference_time_ms": round(float(result.speed.get("inference", 0)), 2),
            "model": "YOLO26n Semantic (PT)",
        }


semantic_model_ops = SemanticModelOpsService()
