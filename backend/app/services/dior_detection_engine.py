"""Ultralytics PT inference adapter for the DIOR horizontal-box model."""

from __future__ import annotations

import hashlib
import io
import json
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


class DiorArtifactError(RuntimeError):
    """Raised when the configured DIOR deployment package is invalid."""


class DiorDetectionEngine:
    """Load one DIOR model and normalize Ultralytics results for the API."""

    engine = "ultralytics-pt"

    def __init__(
        self,
        deploy_dir: Path,
        device: str,
        expected_sha256: str | None = None,
        verify_sha256: bool = True,
    ) -> None:
        self.deploy_dir = Path(deploy_dir).resolve()
        self.model_path = self.deploy_dir / "best.pt"
        self.metadata_path = self.deploy_dir / "metadata.json"
        self.metrics_path = self.deploy_dir / "metrics.json"
        self.device = device
        self._lock = threading.Lock()

        if not self.model_path.is_file() or not self.metadata_path.is_file():
            raise DiorArtifactError("DIOR deployment requires best.pt and metadata.json")
        self.metadata = self._read_json(self.metadata_path)
        self.metrics = self._read_json(self.metrics_path) if self.metrics_path.is_file() else {}
        self._validate_metadata(self.metadata)

        self.model_sha256 = self._sha256(self.model_path)
        declared = expected_sha256 or self._declared_sha256()
        if verify_sha256 and declared and self.model_sha256.lower() != declared.lower():
            raise DiorArtifactError("DIOR best.pt SHA256 mismatch")

        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise DiorArtifactError("ultralytics is not installed in the backend environment") from exc

        self.model = YOLO(str(self.model_path))
        if getattr(self.model, "task", None) != "detect":
            raise DiorArtifactError("DIOR checkpoint is not an object-detection model")
        model_names = self._normalize_names(getattr(self.model, "names", {}))
        if model_names != self.metadata["classes"]:
            raise DiorArtifactError("DIOR checkpoint class order does not match metadata.json")

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DiorArtifactError(f"Invalid DIOR artifact: {path.name}") from exc
        if not isinstance(value, dict):
            raise DiorArtifactError(f"Invalid DIOR artifact object: {path.name}")
        return value

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    def _declared_sha256(self) -> str | None:
        path = self.deploy_dir / "SHA256SUMS.txt"
        if not path.is_file():
            return None
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[-1].lstrip("*") == "best.pt":
                return parts[0]
        return None

    @staticmethod
    def _normalize_names(names: Any) -> list[str]:
        if isinstance(names, dict):
            return [str(names[index]) for index in sorted(names)]
        if isinstance(names, (list, tuple)):
            return [str(item) for item in names]
        return []

    @staticmethod
    def _validate_metadata(metadata: dict[str, Any]) -> None:
        if metadata.get("task") != "detection":
            raise DiorArtifactError("DIOR metadata task must be detection")
        classes = metadata.get("classes")
        if not isinstance(classes, list) or len(classes) != 20 or not all(
            isinstance(item, str) and item for item in classes
        ):
            raise DiorArtifactError("DIOR metadata must declare 20 ordered classes")
        if not isinstance(metadata.get("input_size"), int):
            raise DiorArtifactError("DIOR metadata input_size is invalid")

    def predict(
        self,
        image: Image.Image,
        conf: float,
        iou: float,
        image_size: int,
    ) -> dict[str, Any]:
        source = np.asarray(image.convert("RGB"))
        started = time.perf_counter()
        with self._lock:
            results = self.model.predict(
                source=source,
                conf=conf,
                iou=iou,
                imgsz=image_size,
                device=self.device,
                verbose=False,
            )
        elapsed_ms = (time.perf_counter() - started) * 1000
        if not results:
            raise RuntimeError("DIOR inference returned no result")

        result = results[0]
        detections: list[dict[str, Any]] = []
        boxes = getattr(result, "boxes", None)
        if boxes is not None:
            xyxy = boxes.xyxy.detach().cpu().tolist()
            confidences = boxes.conf.detach().cpu().tolist()
            class_ids = boxes.cls.detach().cpu().tolist()
            for coords, confidence, class_value in zip(xyxy, confidences, class_ids):
                class_id = int(class_value)
                detections.append(
                    {
                        "class_id": class_id,
                        "class_name": self.metadata["classes"][class_id],
                        "confidence": round(float(confidence), 6),
                        "bbox": {
                            "x1": round(float(coords[0]), 2),
                            "y1": round(float(coords[1]), 2),
                            "x2": round(float(coords[2]), 2),
                            "y2": round(float(coords[3]), 2),
                        },
                    }
                )

        plotted_bgr = result.plot()
        annotated = Image.fromarray(plotted_bgr[:, :, ::-1])
        buffer = io.BytesIO()
        annotated.save(buffer, format="JPEG", quality=90)
        annotated.close()
        return {
            "detections": detections,
            "annotated_jpeg": buffer.getvalue(),
            "inference_time_ms": round(elapsed_ms, 2),
            "width": image.width,
            "height": image.height,
        }

