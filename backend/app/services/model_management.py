"""Filesystem-only, read-only model management service."""

from __future__ import annotations

import csv
import io
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config.settings import Settings, settings

DEPLOYED_MODEL_ID = "loveda-baseline-e50-i512-b2"
TRAINING_MODEL_ID = "loveda-v2-hr1024-yolo26s-e50-b4"
DEPLOY_FILES = (
    "best.pt",
    "best_dynamic.onnx",
    "metadata.json",
    "metrics.json",
    "training_args.yaml",
    "export_status.json",
    "SHA256SUMS.txt",
)
RUN_FILES = ("args.yaml", "results.csv", "weights/best.pt", "weights/last.pt", "experiment_report.json")
PARAMETER_ALLOWLIST = (
    "task", "model", "epochs", "patience", "batch", "imgsz", "optimizer", "lr0",
    "weight_decay", "warmup_epochs", "mosaic", "mixup", "device", "workers", "amp",
    "deterministic", "pretrained", "seed", "close_mosaic", "mask_ratio",
)
CURVE_COLUMNS = {
    "metrics/mIoU": "miou",
    "metrics/pixel_acc": "pixel_accuracy",
    "train/ce_loss": "train_ce_loss",
    "train/dice_loss": "train_dice_loss",
    "val/ce_loss": "val_ce_loss",
    "val/dice_loss": "val_dice_loss",
}


class ModelManagementPathError(ValueError):
    """Raised when a configured model directory escapes its trusted root."""


class ModelManagementService:
    """Inspect exactly two configured model directories without loading model binaries."""

    def __init__(self, config: Settings = settings, now_provider=None):
        self.config = config
        self._now = now_provider or (lambda: datetime.now(timezone.utc))
        self.root = config.model_management_trusted_root_path.resolve()
        self.deploy_dir = self._resolve_configured_dir(config.MODEL_MANAGEMENT_DEPLOY_DIR)
        self.run_dir = self._resolve_configured_dir(config.MODEL_MANAGEMENT_TRAINING_RUN_DIR)

    def _resolve_configured_dir(self, configured: str) -> Path:
        candidate = Path(configured)
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            resolved = (self.root / candidate).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ModelManagementPathError("模型目录必须位于可信根目录内") from exc
        return resolved

    def _allowed_file(self, directory: Path, relative_name: str, allowlist: tuple[str, ...]) -> Path:
        if relative_name not in allowlist:
            raise ModelManagementPathError("拒绝访问非白名单文件")
        path = (directory / relative_name).resolve()
        try:
            path.relative_to(directory)
        except ValueError as exc:
            raise ModelManagementPathError("文件路径逃逸模型目录") from exc
        return path

    def _snapshot(self, path: Path) -> bytes | None:
        """Read one bounded snapshot from an ordinary file; never lock or write it."""
        try:
            with path.open("rb") as stream:
                data = stream.read(self.config.MODEL_MANAGEMENT_MAX_TEXT_BYTES + 1)
        except (FileNotFoundError, IsADirectoryError, PermissionError, OSError):
            return None
        if len(data) > self.config.MODEL_MANAGEMENT_MAX_TEXT_BYTES:
            return None
        return data

    def _json(self, directory: Path, name: str, allowlist: tuple[str, ...]) -> dict[str, Any] | None:
        data = self._snapshot(self._allowed_file(directory, name, allowlist))
        if data is None:
            return None
        try:
            value = json.loads(data.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return self._sanitize(value) if isinstance(value, dict) else None

    def _yaml_parameters(self, directory: Path, name: str, allowlist: tuple[str, ...]) -> dict[str, Any]:
        """Parse only top-level scalar allowlisted keys from Ultralytics args YAML."""
        data = self._snapshot(self._allowed_file(directory, name, allowlist))
        if data is None:
            return {}
        try:
            lines = data.decode("utf-8-sig").splitlines()
        except UnicodeDecodeError:
            return {}
        parameters: dict[str, Any] = {}
        for line in lines:
            if not line or line[0].isspace() or line.lstrip().startswith("#") or ":" not in line:
                continue
            key, raw = line.split(":", 1)
            key = key.strip()
            if key not in PARAMETER_ALLOWLIST:
                continue
            parameters[key] = self._sanitize(self._yaml_scalar(raw.strip()))
        return parameters

    @staticmethod
    def _yaml_scalar(raw: str) -> Any:
        if not raw or raw in {"null", "Null", "NULL", "~"}:
            return None
        if raw.lower() in {"true", "false"}:
            return raw.lower() == "true"
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {"'", '"'}:
            return raw[1:-1]
        try:
            return int(raw)
        except ValueError:
            try:
                number = float(raw)
                return number if math.isfinite(number) else None
            except ValueError:
                return raw.split(" #", 1)[0].strip()

    def _sanitize(self, value: Any) -> Any:
        """Remove non-finite values and prevent absolute filesystem paths leaking."""
        if isinstance(value, float):
            return value if math.isfinite(value) else None
        if isinstance(value, dict):
            return {str(key): self._sanitize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._sanitize(item) for item in value]
        if isinstance(value, str):
            looks_windows_absolute = len(value) >= 3 and value[1:3] in {":\\", ":/"}
            if os.path.isabs(value) or looks_windows_absolute:
                return Path(value.replace("\\", "/")).name
        return value

    @staticmethod
    def _finite_float(value: str | None) -> float | None:
        try:
            number = float(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None
        return number if number is not None and math.isfinite(number) else None

    def _curve(self) -> tuple[list[dict[str, Any]], list[str]]:
        path = self._allowed_file(self.run_dir, "results.csv", RUN_FILES)
        data = self._snapshot(path)
        if data is None:
            return [], ["results.csv 不存在、不可读或超过大小限制"]
        warnings: list[str] = []
        # A writer may be appending: only newline-terminated records belong to this snapshot.
        if data and not data.endswith((b"\n", b"\r")):
            _, separator, _tail = data.rpartition(b"\n")
            data = data[: len(data) - len(_tail)] if separator else b""
            warnings.append("已忽略 results.csv 的不完整尾行")
        try:
            rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig", errors="strict"))))
        except (UnicodeDecodeError, csv.Error):
            return [], warnings + ["results.csv 快照无法解析"]
        if not rows:
            return [], warnings
        header = [item.strip() for item in rows[0]]
        if "epoch" not in header:
            return [], warnings + ["results.csv 缺少 epoch 字段"]
        by_epoch: dict[int, dict[str, Any]] = {}
        for values in rows[1 : self.config.MODEL_MANAGEMENT_MAX_CSV_ROWS + 1]:
            if len(values) != len(header):
                warnings.append("已忽略字段数不匹配的 CSV 行")
                continue
            record = dict(zip(header, (item.strip() for item in values)))
            epoch_value = self._finite_float(record.get("epoch"))
            if epoch_value is None or not epoch_value.is_integer() or epoch_value < 0:
                warnings.append("已忽略 epoch 无效的 CSV 行")
                continue
            point: dict[str, Any] = {"epoch": int(epoch_value)}
            invalid_metric = False
            for csv_name, api_name in CURVE_COLUMNS.items():
                raw_metric = record.get(csv_name)
                metric = self._finite_float(raw_metric)
                if raw_metric not in (None, "") and metric is None:
                    invalid_metric = True
                    break
                point[api_name] = metric
            if invalid_metric:
                warnings.append("已忽略包含无效或非有限指标的 CSV 行")
                continue
            # Deterministic duplicate handling: the last complete valid row wins.
            by_epoch[point["epoch"]] = point
        if len(rows) - 1 > self.config.MODEL_MANAGEMENT_MAX_CSV_ROWS:
            warnings.append("results.csv 已按最大行数截断")
        return [by_epoch[key] for key in sorted(by_epoch)], list(dict.fromkeys(warnings))

    def _declared_hashes(self) -> dict[str, str]:
        data = self._snapshot(self._allowed_file(self.deploy_dir, "SHA256SUMS.txt", DEPLOY_FILES))
        if data is None:
            return {}
        hashes: dict[str, str] = {}
        for line in data.decode("utf-8", errors="replace").splitlines():
            parts = line.strip().split()
            if len(parts) >= 2 and len(parts[0]) == 64:
                name = parts[-1].lstrip("*").replace("\\", "/").rsplit("/", 1)[-1]
                if name in DEPLOY_FILES and all(char in "0123456789abcdefABCDEF" for char in parts[0]):
                    hashes[name] = parts[0].lower()
        return hashes

    def _artifacts(self, directory: Path, allowlist: tuple[str, ...], hashes=None) -> list[dict[str, Any]]:
        result = []
        hashes = hashes or {}
        for name in allowlist:
            path = self._allowed_file(directory, name, allowlist)
            try:
                stat = path.stat()
                exists = path.is_file()
            except OSError:
                stat = None
                exists = False
            result.append({
                "name": name,
                "exists": exists,
                "size_bytes": stat.st_size if exists and stat else None,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc) if exists and stat else None,
                "declared_sha256": hashes.get(name),
            })
        return result

    def deployed_model(self) -> dict[str, Any]:
        metadata = self._json(self.deploy_dir, "metadata.json", DEPLOY_FILES)
        metrics = self._json(self.deploy_dir, "metrics.json", DEPLOY_FILES)
        export = self._json(self.deploy_dir, "export_status.json", DEPLOY_FILES)
        hashes = self._declared_hashes()
        artifacts = self._artifacts(self.deploy_dir, DEPLOY_FILES, hashes)
        complete = all(item["exists"] for item in artifacts)
        export_ok = bool(export and export.get("success") is True and export.get("onnx_checker") == "passed")
        overall = (metrics or {}).get("overall", {})
        warnings = []
        if not complete:
            warnings.append("部署目录产物不完整")
        if not export_ok:
            warnings.append("ONNX 导出或 checker 未声明成功")
        best_epoch = (metadata or {}).get("best_epoch")
        params = self._yaml_parameters(self.deploy_dir, "training_args.yaml", DEPLOY_FILES)
        target = params.get("epochs") if isinstance(params.get("epochs"), int) else None
        return {
            "id": DEPLOYED_MODEL_ID,
            "display_name": "LoveDA 语义分割部署基线",
            "source_type": "deployed_artifact",
            "lifecycle_status": "deployed" if complete and export_ok else "incomplete",
            "deployment_status": "deployed" if complete and export_ok else "not_deployed",
            "stale": False,
            "epoch_target": target,
            "epochs_recorded": target or 0,
            "current_epoch": best_epoch,
            "progress": 100.0 if complete and export_ok else None,
            "latest_miou": self._number(overall.get("miou")),
            "best_miou": self._number(overall.get("miou")),
            "pixel_accuracy": self._number(overall.get("pixel_accuracy")),
            "training_parameters": params,
            "artifacts": artifacts,
            "warnings": warnings,
            "training_curve": [],
            "metadata": metadata,
            "metrics": metrics,
            "export_status": export,
            "report": None,
        }

    @staticmethod
    def _number(value: Any) -> float | None:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            number = float(value)
            return number if math.isfinite(number) else None
        return None

    def training_model(self) -> dict[str, Any]:
        params = self._yaml_parameters(self.run_dir, "args.yaml", RUN_FILES)
        report = self._json(self.run_dir, "experiment_report.json", RUN_FILES)
        curve, warnings = self._curve()
        artifacts = self._artifacts(self.run_dir, RUN_FILES)
        target = params.get("epochs") if isinstance(params.get("epochs"), int) else None
        latest = curve[-1] if curve else None
        best = max((point for point in curve if point.get("miou") is not None), key=lambda p: p["miou"], default=None)
        recorded = len(curve)
        current_epoch = latest["epoch"] if latest else None
        latest_activity = max((item["modified_at"] for item in artifacts if item["modified_at"]), default=None)
        age = (self._now() - latest_activity).total_seconds() if latest_activity else float("inf")
        stale = report is None and age > self.config.MODEL_MANAGEMENT_STALE_SECONDS
        if report is not None:
            status = str(report.get("status") or "completed")
        elif target and current_epoch is not None and current_epoch >= target:
            status = "finalizing"
        else:
            status = "training"
        if stale:
            warnings.append("训练产物已超过 stale 窗口；未查询或控制训练进程")
        progress = min(100.0, recorded / target * 100) if target and target > 0 else None
        return {
            "id": TRAINING_MODEL_ID,
            "display_name": "LoveDA V2 1024px YOLO26s 训练模型",
            "source_type": "training_run",
            "lifecycle_status": status,
            "deployment_status": "not_deployed",
            "stale": stale,
            "epoch_target": target,
            "epochs_recorded": recorded,
            "current_epoch": current_epoch,
            "progress": progress,
            "latest_miou": latest.get("miou") if latest else None,
            "best_miou": best.get("miou") if best else self._number((report or {}).get("best_miou")),
            "pixel_accuracy": latest.get("pixel_accuracy") if latest else self._number((report or {}).get("best_pixel_accuracy")),
            "training_parameters": params,
            "artifacts": artifacts,
            "warnings": list(dict.fromkeys(warnings)),
            "training_curve": curve,
            "metadata": None,
            "metrics": None,
            "export_status": None,
            "report": report,
        }

    def models(self) -> list[dict[str, Any]]:
        return [self.deployed_model(), self.training_model()]

    def get(self, model_id: str) -> dict[str, Any] | None:
        return next((model for model in self.models() if model["id"] == model_id), None)

    def overview(self) -> dict[str, Any]:
        models = self.models()
        return {
            "total": len(models),
            "deployed": sum(model["deployment_status"] == "deployed" for model in models),
            "training": sum(model["lifecycle_status"] == "training" for model in models),
            "finalizing": sum(model["lifecycle_status"] == "finalizing" for model in models),
            "stale": sum(model["stale"] for model in models),
            "models": models,
        }


model_management_service = ModelManagementService()
