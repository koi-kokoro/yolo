"""Reproducible Day07 evaluation, ONNX export/validation, and deployment packaging.

Run with the project YOLO environment from the workspace root:
D:\\programfile\\anaconda\\envs\\yolo\\python.exe src/training/loveda_semantic/day07_evaluate_export.py
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import matplotlib.pyplot as plt
import numpy as np
import torch
import yaml
from ultralytics import YOLO

from common import CLASS_NAMES, IGNORE_COLOR, PALETTE

ROOT = Path(__file__).resolve().parent
# Defaults preserve the original Day07 baseline workflow. CLI arguments override these
# globals before any model or output is opened, allowing isolated V2 evaluation.
WEIGHT = ROOT / "runs/baseline_e50_i512_b2/weights/best.pt"
DATA_YAML = ROOT / "loveda7.yaml"
DATA_ROOT = ROOT / "data/loveda_yolo_semantic"
ARTIFACTS = ROOT / "artifacts/baseline_e50_i512_b2"
DEPLOY = ARTIFACTS / "deploy"
IMGSZ = 512
BATCH = 2
DEVICE: str | int = 0 if torch.cuda.is_available() else "cpu"
VERSION = "baseline-e50-i512-b2"
IGNORE = 255
NC = 7
SEED = 26


def jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    return value


def confusion_update(matrix: np.ndarray, target: np.ndarray, prediction: np.ndarray) -> tuple[int, int]:
    valid = target != IGNORE
    target = target[valid].astype(np.int64)
    prediction = prediction[valid].astype(np.int64)
    # The trained Ultralytics semantic head has an eighth internal ignore/background channel.
    # Results metadata names class 7 "background"; collapse it to public class 0.
    prediction[prediction == NC] = 0
    if np.any((target < 0) | (target >= NC)) or np.any((prediction < 0) | (prediction >= NC)):
        raise ValueError("Label outside the public 0..6 range after ignore filtering/remapping")
    matrix += np.bincount(NC * target + prediction, minlength=NC * NC).reshape(NC, NC)
    return int(valid.sum()), int((~valid).sum())


def metrics(matrix: np.ndarray) -> dict[str, Any]:
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
            {"class_id": i, "class_name": CLASS_NAMES[i], "iou": iou[i], "dice_f1": dice[i],
             "precision": precision[i], "recall": recall[i], "support_pixels": int(gt[i])}
            for i in range(NC)
        ],
        "confusion_matrix": matrix.astype(np.int64),
    }


def colorize(mask: np.ndarray, ignored: np.ndarray | None = None) -> np.ndarray:
    safe = mask.copy()
    safe[safe >= NC] = 0
    rgb = PALETTE[safe]
    if ignored is not None:
        rgb[ignored] = IGNORE_COLOR
    return rgb


def save_confusion(matrix: np.ndarray, output: Path, normalized: bool = False) -> None:
    values = matrix.astype(float)
    if normalized:
        values = np.divide(values, values.sum(1, keepdims=True), out=np.zeros_like(values), where=values.sum(1, keepdims=True) > 0)
    fig, ax = plt.subplots(figsize=(9, 8))
    image = ax.imshow(values, cmap="Blues")
    fig.colorbar(image, ax=ax)
    ax.set(xticks=range(NC), yticks=range(NC), xticklabels=CLASS_NAMES, yticklabels=CLASS_NAMES,
           xlabel="Predicted", ylabel="Ground truth", title="Pixel Confusion Matrix" + (" (row normalized)" if normalized else ""))
    plt.setp(ax.get_xticklabels(), rotation=35, ha="right")
    threshold = values.max() * 0.55 if values.size else 0
    for row in range(NC):
        for col in range(NC):
            text = f"{values[row, col]:.3f}" if normalized else f"{int(values[row, col]):,}"
            ax.text(col, row, text, ha="center", va="center", fontsize=7, color="white" if values[row, col] > threshold else "black")
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def predict_onnx(session: Any, path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(path)
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(rgb, (IMGSZ, IMGSZ), interpolation=cv2.INTER_LINEAR)
    tensor = np.ascontiguousarray(resized.transpose(2, 0, 1)[None]).astype(np.float32) / 255.0
    output = session.run(None, {session.get_inputs()[0].name: tensor})[0]
    prediction = np.squeeze(output).astype(np.uint8)
    if prediction.ndim != 2:
        raise ValueError(f"Unexpected ONNX semantic prediction shape for {path}: {output.shape}")
    return prediction


def evaluate(model: Any) -> dict[str, Any]:
    matrices = {"overall": np.zeros((NC, NC), dtype=np.int64), "Urban": np.zeros((NC, NC), dtype=np.int64), "Rural": np.zeros((NC, NC), dtype=np.int64)}
    counts = {key: {"images": 0, "ignored_pixels": 0} for key in matrices}
    sample_dir = ARTIFACTS / "sample_predictions"
    sample_dir.mkdir(parents=True, exist_ok=True)
    for region in ("Urban", "Rural"):
        images = sorted((DATA_ROOT / "images/val" / region).glob("*.png"))
        if not images:
            raise FileNotFoundError(f"No validation images for {region}")
        sample_indices = set(np.linspace(0, len(images) - 1, min(4, len(images)), dtype=int).tolist())
        stream = None if WEIGHT.suffix.lower() == ".onnx" else model.predict(
            source=[str(path) for path in images], imgsz=IMGSZ, batch=BATCH,
            device=DEVICE, workers=0, verbose=False, stream=True
        )
        iterator = ((path, None) for path in images) if stream is None else zip(images, stream)
        for index, (path, result) in enumerate(iterator):
            mask_path = DATA_ROOT / "masks/val" / region / path.name
            target = cv2.imread(str(mask_path), cv2.IMREAD_UNCHANGED)
            if target is None:
                raise FileNotFoundError(mask_path)
            # Converted masks are normally grayscale; tolerate palette/RGB PNG readers by
            # selecting an identical channel, while rejecting genuinely colored labels.
            if target.ndim == 3:
                if target.shape[2] == 1:
                    target = target[..., 0]
                elif target.shape[2] >= 3:
                    if not np.all(target[..., 0] == target[..., 1]) or not np.all(target[..., 0] == target[..., 2]):
                        raise ValueError(f"Mask is not grayscale: {mask_path}")
                    target = target[..., 0]
                else:
                    raise ValueError(f"Unexpected mask shape: {mask_path}: {target.shape}")
            prediction = predict_onnx(model, path) if result is None else np.squeeze(result.semantic_mask.data.detach().cpu().numpy()).astype(np.uint8)
            if prediction.ndim != 2:
                raise ValueError(f"Unexpected semantic prediction shape for {path}: {prediction.shape}")
            if prediction.shape != target.shape:
                prediction = cv2.resize(prediction, (target.shape[1], target.shape[0]), interpolation=cv2.INTER_NEAREST)
            valid, ignored = confusion_update(matrices[region], target, prediction)
            confusion_update(matrices["overall"], target, prediction)
            for key in (region, "overall"):
                counts[key]["images"] += 1
                counts[key]["ignored_pixels"] += ignored
            if index in sample_indices:
                image = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
                shown_pred = prediction.copy(); shown_pred[shown_pred == NC] = 0
                panel = np.concatenate((image, colorize(target, target == IGNORE), colorize(shown_pred)), axis=1)
                cv2.imwrite(str(sample_dir / f"{region}_{path.stem}_image_gt_pred.png"), cv2.cvtColor(panel, cv2.COLOR_RGB2BGR))
    report = {}
    for domain, matrix in matrices.items():
        report[domain] = metrics(matrix)
        report[domain].update(counts[domain])
    return report


def write_metrics(report: dict[str, Any]) -> None:
    (ARTIFACTS / "metrics.json").write_text(json.dumps(report, default=jsonable, ensure_ascii=False, indent=2), encoding="utf-8")
    with (ARTIFACTS / "metrics_summary.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["domain", "images", "valid_pixels", "ignored_pixels", "miou", "pixel_accuracy", "mean_dice_f1"])
        writer.writeheader()
        for domain, item in report.items():
            writer.writerow({"domain": domain, **{key: item[key] for key in writer.fieldnames if key != "domain"}})
    with (ARTIFACTS / "per_class_metrics.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields = ["domain", "class_id", "class_name", "iou", "dice_f1", "precision", "recall", "support_pixels"]
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader()
        for domain, item in report.items():
            for row in item["per_class"]: writer.writerow({"domain": domain, **row})
    with (ARTIFACTS / "confusion_matrix.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle); writer.writerow(["ground_truth\\prediction", *CLASS_NAMES])
        for name, row in zip(CLASS_NAMES, report["overall"]["confusion_matrix"]): writer.writerow([name, *row])
    matrix = np.asarray(report["overall"]["confusion_matrix"])
    normalized = np.divide(matrix, matrix.sum(1, keepdims=True), out=np.zeros_like(matrix, dtype=float), where=matrix.sum(1, keepdims=True) > 0)
    with (ARTIFACTS / "confusion_matrix_normalized.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle); writer.writerow(["ground_truth\\prediction", *CLASS_NAMES])
        for name, row in zip(CLASS_NAMES, normalized): writer.writerow([name, *[f"{value:.12g}" for value in row]])
    save_confusion(matrix, ARTIFACTS / "confusion_matrix.png")
    save_confusion(matrix, ARTIFACTS / "confusion_matrix_normalized.png", True)
    x = np.arange(NC); width = 0.25
    fig, ax = plt.subplots(figsize=(11, 6))
    for offset, domain in enumerate(("overall", "Urban", "Rural")):
        ax.bar(x + (offset - 1) * width, [row["iou"] for row in report[domain]["per_class"]], width, label=domain)
    ax.set(xticks=x, xticklabels=CLASS_NAMES, ylim=(0, 1), ylabel="IoU", title="Per-class IoU by domain"); ax.legend(); fig.tight_layout()
    fig.savefig(ARTIFACTS / "per_class_iou_by_domain.png", dpi=180); plt.close(fig)


def versions() -> dict[str, Any]:
    packages = {}
    for name in ("torch", "ultralytics", "numpy", "opencv-python", "onnx", "onnxruntime"):
        try:
            from importlib.metadata import version
            packages[name] = version(name)
        except Exception:
            packages[name] = None
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "python": sys.version, "executable": sys.executable,
            "platform": platform.platform(), "cuda_available": torch.cuda.is_available(), "cuda": torch.version.cuda,
            "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None, "packages": packages}


def export_onnx(model: YOLO, sample_path: Path) -> dict[str, Any]:
    status: dict[str, Any] = {"success": False, "requested_dynamic_batch": True, "imgsz": IMGSZ}
    try:
        exported = Path(model.export(format="onnx", imgsz=IMGSZ, dynamic=True, batch=1, simplify=False, device="cpu"))
        target = DEPLOY / "best_dynamic.onnx"
        shutil.copy2(exported, target)
        import onnx
        graph = onnx.load(str(target)); onnx.checker.check_model(graph)
        status.update(success=True, path=str(target), onnx_checker="passed", inputs=[item.name for item in graph.graph.input], outputs=[item.name for item in graph.graph.output])
        try:
            import onnxruntime as ort
            session = ort.InferenceSession(str(target), providers=["CPUExecutionProvider"])
            image = cv2.cvtColor(cv2.imread(str(sample_path)), cv2.COLOR_BGR2RGB)
            image = cv2.resize(image, (IMGSZ, IMGSZ), interpolation=cv2.INTER_LINEAR)
            tensor = np.ascontiguousarray(image.transpose(2, 0, 1)[None]).astype(np.float32) / 255.0
            # Official export may leave the in-memory module on its prior CUDA device.
            # Compare on CPU to match the ONNX Runtime CPU provider deterministically.
            model.model.to("cpu").eval()
            with torch.no_grad(): pt_raw = model.model(torch.from_numpy(tensor))
            if isinstance(pt_raw, (tuple, list)): pt_raw = pt_raw[0]
            pt_logits = pt_raw.detach().cpu()
            pt_mask = torch.nn.functional.interpolate(pt_logits, size=(IMGSZ, IMGSZ), mode="bilinear", align_corners=False).argmax(1).numpy()
            ort_out = session.run(None, {session.get_inputs()[0].name: tensor})[0]
            # The official semantic exporter emits the postprocessed class map rather
            # than logits, so numerical validation is exact class-map agreement.
            ort_mask = ort_out.astype(np.int64)
            if ort_mask.ndim == 2: ort_mask = ort_mask[None]
            status["runtime_validation"] = {"available": True, "provider": "CPUExecutionProvider", "input_shape": list(tensor.shape),
                "pytorch_raw_logits_shape": list(pt_logits.shape), "pytorch_mask_shape": list(pt_mask.shape), "onnx_output_shape": list(ort_out.shape),
                "onnx_output_semantics": "postprocessed class-id map", "class_map_pixel_agreement": float(np.mean(pt_mask == ort_mask)),
                "class_map_max_abs_difference": int(np.max(np.abs(pt_mask - ort_mask)))}
        except Exception as error:
            status["runtime_validation"] = {"available": False, "error": repr(error)}
    except Exception as error:
        status.update(error=repr(error), limitation="Ultralytics official model.export semantic ONNX path failed; PT remains the supported deployment artifact. No site-packages were modified.")
    return status


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""): digest.update(chunk)
    return digest.hexdigest()


def package(report: dict[str, Any], export: dict[str, Any]) -> None:
    shutil.copy2(WEIGHT, DEPLOY / "best.pt")
    shutil.copy2(DATA_YAML, DEPLOY / "loveda7.yaml")
    args = WEIGHT.parents[1] / "args.yaml"
    if args.exists(): shutil.copy2(args, DEPLOY / "training_args.yaml")
    metadata = {"task": "semantic-segmentation", "model": "YOLO26n Semantic", "input": {"layout": "NCHW", "size": [IMGSZ, IMGSZ], "color": "RGB", "dtype": "float32", "scale": "0..1"},
        "classes": [{"id": i, "name": name, "rgb": PALETTE[i].tolist()} for i, name in enumerate(CLASS_NAMES)], "ignore_label": IGNORE,
        "internal_output_note": "The checkpoint has 8 logits; public classes are 0..6. Internal prediction 7 is named background by checkpoint metadata and is collapsed to class 0 for evaluation/deployment.",
        "best_epoch": 20, "metrics": {key: {name: report[key][name] for name in ("miou", "pixel_accuracy", "mean_dice_f1")} for key in report}, "onnx_export": export}
    (DEPLOY / "metadata.json").write_text(json.dumps(metadata, default=jsonable, ensure_ascii=False, indent=2), encoding="utf-8")
    (DEPLOY / "environment.json").write_text(json.dumps(versions(), ensure_ascii=False, indent=2), encoding="utf-8")
    readme = """# YOLO26n Semantic LoveDA deployment\n\n## PT inference (recommended fallback)\nLoad `best.pt` with `ultralytics.YOLO`, call `predict(source, imgsz=512)`, and read `result.semantic_mask.data`. Resize with nearest-neighbor to the original image when needed. Collapse internal label 7 to public background (0). Public labels are documented in `metadata.json`; 255 is ground-truth ignore only.\n\n## ONNX inference\nInput is RGB float32 NCHW scaled to [0,1], nominally 512x512. Run the ONNX output logits, take argmax over channel axis, collapse label 7 to 0, and nearest-neighbor resize to source dimensions. Consult `export_status.json` before using ONNX.\n"""
    (DEPLOY / "INFERENCE.md").write_text(readme, encoding="utf-8")
    shutil.copy2(ARTIFACTS / "metrics.json", DEPLOY / "metrics.json")
    (DEPLOY / "export_status.json").write_text(json.dumps(export, ensure_ascii=False, indent=2), encoding="utf-8")
    files = sorted(path for path in DEPLOY.rglob("*") if path.is_file() and path.name != "SHA256SUMS.txt")
    (DEPLOY / "SHA256SUMS.txt").write_text("".join(f"{sha256(path)}  {path.relative_to(DEPLOY).as_posix()}\n" for path in files), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Independent full-split LoveDA semantic evaluation")
    parser.add_argument("--model", type=Path, default=WEIGHT, help="Ultralytics PT or ONNX model")
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT, help="Converted LoveDA semantic dataset root")
    parser.add_argument("--output-dir", type=Path, default=ARTIFACTS, help="Isolated evaluation artifact directory")
    parser.add_argument("--imgsz", type=int, default=IMGSZ)
    parser.add_argument("--batch", type=int, default=BATCH)
    parser.add_argument("--device", default=str(DEVICE), help="Ultralytics device, e.g. 0 or cpu")
    parser.add_argument("--version", default=VERSION)
    parser.add_argument("--expected-images", type=int, default=None)
    parser.add_argument("--evaluate-only", action="store_true", help="Do not export/package or modify deploy artifacts")
    return parser.parse_args()


def validate_report(report: dict[str, Any], expected_images: int | None) -> dict[str, Any]:
    matrix = np.asarray(report["overall"]["confusion_matrix"], dtype=np.int64)
    checks = {
        "expected_image_count": expected_images,
        "actual_image_count": report["overall"]["images"],
        "image_count_matches": expected_images is None or report["overall"]["images"] == expected_images,
        "matrix_sum": int(matrix.sum()),
        "reported_valid_pixels": report["overall"]["valid_pixels"],
        "matrix_sum_matches_valid_pixels": int(matrix.sum()) == report["overall"]["valid_pixels"],
        "domain_images_sum_matches": report["Urban"]["images"] + report["Rural"]["images"] == report["overall"]["images"],
        "domain_matrices_sum_matches": np.array_equal(
            np.asarray(report["Urban"]["confusion_matrix"]) + np.asarray(report["Rural"]["confusion_matrix"]), matrix
        ),
    }
    recomputed = metrics(matrix)
    checks["metrics_recompute_matches"] = all(
        np.isclose(report["overall"][key], recomputed[key], rtol=0, atol=1e-12)
        for key in ("miou", "pixel_accuracy", "mean_dice_f1")
    )
    scalar_values = [
        report[domain][key]
        for domain in ("overall", "Urban", "Rural")
        for key in ("miou", "pixel_accuracy", "mean_dice_f1")
    ]
    scalar_values.extend(
        row[key]
        for domain in ("overall", "Urban", "Rural")
        for row in report[domain]["per_class"]
        for key in ("iou", "dice_f1", "precision", "recall")
    )
    checks["metrics_finite_and_bounded"] = all(np.isfinite(value) and 0 <= value <= 1 for value in scalar_values)
    checks["passed"] = all(value for key, value in checks.items() if key.endswith("matches") or key == "metrics_finite_and_bounded")
    if not checks["passed"]:
        raise RuntimeError(f"Evaluation integrity check failed: {checks}")
    return checks


def main() -> None:
    global WEIGHT, DATA_ROOT, ARTIFACTS, DEPLOY, IMGSZ, BATCH, DEVICE, VERSION
    args = parse_args()
    WEIGHT = args.model.resolve(); DATA_ROOT = args.data_root.resolve(); ARTIFACTS = args.output_dir.resolve()
    DEPLOY = ARTIFACTS / "deploy"; IMGSZ = args.imgsz; BATCH = args.batch
    DEVICE = int(args.device) if str(args.device).isdigit() else args.device; VERSION = args.version
    if not WEIGHT.is_file(): raise FileNotFoundError(WEIGHT)
    started = datetime.now(timezone.utc)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    np.random.seed(SEED); torch.manual_seed(SEED)
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(SEED)
    model_hash = sha256(WEIGHT)
    if WEIGHT.suffix.lower() == ".onnx":
        import onnxruntime as ort
        session_options = ort.SessionOptions()
        session_options.intra_op_num_threads = 1
        session_options.inter_op_num_threads = 1
        model = ort.InferenceSession(str(WEIGHT), sess_options=session_options, providers=["CPUExecutionProvider"])
    else:
        model = YOLO(str(WEIGHT), task="semantic")
    report = evaluate(model); write_metrics(report)
    checks = validate_report(report, args.expected_images)
    environment = versions()
    (ARTIFACTS / "environment.json").write_text(json.dumps(environment, ensure_ascii=False, indent=2), encoding="utf-8")
    export = None
    if not args.evaluate_only:
        DEPLOY.mkdir(parents=True, exist_ok=True)
        sample = sorted((DATA_ROOT / "images/val/Urban").glob("*.png"))[0]
        export = export_onnx(model, sample)
        (ARTIFACTS / "export_status.json").write_text(json.dumps(export, ensure_ascii=False, indent=2), encoding="utf-8")
        package(report, export)
    command = " ".join([str(Path(sys.executable)), *sys.argv])
    artifacts = sorted(path for path in ARTIFACTS.rglob("*") if path.is_file() and path.name != "evaluation_manifest.json")
    manifest = {
        "schema_version": 1, "status": "completed", "model_version": VERSION,
        "model": {"path": str(WEIGHT), "format": WEIGHT.suffix.lower().lstrip("."), "sha256": model_hash},
        "dataset": {"name": "LoveDA", "split": "Val", "domains": ["Urban", "Rural"],
                    "root": str(DATA_ROOT), "images": report["overall"]["images"], "valid_pixels": report["overall"]["valid_pixels"],
                    "ignore_label": IGNORE, "label_mapping": "source 0->255; source 1..7->public 0..6"},
        "inference": {"imgsz": IMGSZ, "batch": BATCH, "device": str(DEVICE),
                      "runtime": "onnxruntime (direct InferenceSession)" if WEIGHT.suffix.lower() == ".onnx" else "PyTorch via ultralytics",
                      "provider": "CPUExecutionProvider" if WEIGHT.suffix.lower() == ".onnx" else (environment["gpu"] if str(DEVICE) != "cpu" else "CPU")},
        "started_at": started.isoformat(), "finished_at": datetime.now(timezone.utc).isoformat(),
        "code": str(Path(__file__).resolve()), "command": command, "integrity_checks": checks,
        "artifact_sha256": {str(path.relative_to(ARTIFACTS)).replace("\\", "/"): sha256(path) for path in artifacts},
    }
    (ARTIFACTS / "evaluation_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"metrics": {k: {x: report[k][x] for x in ("miou", "pixel_accuracy", "mean_dice_f1")} for k in report},
                      "checks": checks, "model_sha256": model_hash, "export": export, "artifacts": str(ARTIFACTS)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
