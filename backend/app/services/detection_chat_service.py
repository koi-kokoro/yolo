"""Detection chat service — single / batch / ZIP inference.

This service powers the Day 8 smart chat dialog.  It reuses the existing
semantic_model_ops.predict path (ONNX first, PT fallback) and returns results
that can be rendered as cards in the conversation UI.
"""

from __future__ import annotations

import base64
import io
import os
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.exceptions import DomainError
from app.core.logger import get_logger
from app.database.session import SessionLocal
from app.entity.db_models import DetectionScene, DetectionTask, DetectionResult
from app.services.semantic_model_ops import semantic_model_ops
from app.storage.minio_client import MinIOClient

logger = get_logger(__name__)

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _pil_from_path(image_path: str) -> Image.Image:
    """Open an image file and normalize orientation."""
    from PIL import ImageOps

    img = Image.open(image_path)
    return ImageOps.exif_transpose(img).convert("RGB")


def _allowed_image(filename: str) -> bool:
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_IMAGE_EXTENSIONS


def _summarize_statistics(class_statistics: list[dict]) -> dict[str, int]:
    """Return pixel-count summary keyed by class name."""
    summary: dict[str, int] = {}
    for item in class_statistics:
        summary[item["name"]] = summary.get(item["name"], 0) + item.get("pixel_count", 0)
    return summary


class DetectionChatService:
    """Chat-oriented detection inference service."""

    def _infer_one(self, image_path: str) -> dict[str, Any]:
        """Run semantic inference on a single image path."""
        image = _pil_from_path(image_path)
        result = semantic_model_ops.predict(image, use_pt_fallback=True)
        result["filename"] = os.path.basename(image_path)
        result["image_width"] = image.width
        result["image_height"] = image.height
        return result

    def segment_single(
        self,
        image_path: str,
        user_id: int | None = None,
        scene_id: int | None = None,
    ) -> dict[str, Any]:
        """Segment a single image and return a card-friendly payload."""
        inference_result = self._infer_one(image_path)
        class_statistics = inference_result.get("class_statistics", [])

        return {
            "mode": "single",
            "filename": inference_result["filename"],
            "image_width": inference_result["image_width"],
            "image_height": inference_result["image_height"],
            "annotated_image": inference_result.get("annotated_image"),
            "class_statistics": class_statistics,
            "class_counts": _summarize_statistics(class_statistics),
            "inference_time_ms": inference_result.get("inference_time_ms"),
            "model": inference_result.get("model"),
        }

    def segment_batch(
        self,
        image_paths: list[str],
        user_id: int | None = None,
        scene_id: int | None = None,
    ) -> dict[str, Any]:
        """Segment a list of image paths and aggregate results."""
        if not image_paths:
            return {"error": "图片列表为空"}

        per_image = []
        total_inference_ms = 0.0
        aggregated_counts: dict[str, int] = {}

        for path in image_paths:
            if not _allowed_image(path):
                continue
            try:
                result = self._infer_one(path)
                per_image.append({
                    "filename": result["filename"],
                    "image_width": result["image_width"],
                    "image_height": result["image_height"],
                    "annotated_image": result.get("annotated_image"),
                    "class_statistics": result.get("class_statistics", []),
                    "inference_time_ms": result.get("inference_time_ms"),
                })
                total_inference_ms += result.get("inference_time_ms") or 0
                for name, count in _summarize_statistics(result.get("class_statistics", [])).items():
                    aggregated_counts[name] = aggregated_counts.get(name, 0) + count
            except Exception as exc:
                logger.warning("Batch inference failed for %s: %s", path, exc)
                per_image.append({"filename": os.path.basename(path), "error": str(exc)})

        successful = [img for img in per_image if "error" not in img]
        return {
            "mode": "batch",
            "total_images": len(image_paths),
            "successful_images": len(successful),
            "total_inference_ms": round(total_inference_ms, 2),
            "class_counts": aggregated_counts,
            "annotated_images": successful,
        }

    def segment_zip(
        self,
        zip_path: str,
        user_id: int | None = None,
        scene_id: int | None = None,
    ) -> dict[str, Any]:
        """Extract a ZIP archive and segment all images inside."""
        temp_dir = tempfile.mkdtemp(prefix="detection_zip_")
        try:
            with zipfile.ZipFile(zip_path, "r") as archive:
                archive.extractall(temp_dir)

            image_files = []
            for root, _dirs, files in os.walk(temp_dir):
                for fname in files:
                    if _allowed_image(fname):
                        image_files.append(os.path.join(root, fname))

            if not image_files:
                return {"error": "ZIP 文件中没有找到支持的图片"}

            logger.info("ZIP %s contains %d images", zip_path, len(image_files))
            batch_result = self.segment_batch(image_files, user_id=user_id, scene_id=scene_id)
            batch_result["mode"] = "zip"
            batch_result["zip_filename"] = os.path.basename(zip_path)
            return batch_result
        except zipfile.BadZipFile:
            return {"error": f"无效的 ZIP 文件: {zip_path}"}
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


detection_chat_service = DetectionChatService()
