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
import time
from pathlib import Path
from typing import Any

import cv2
from PIL import Image
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.exceptions import DomainError
from app.core.logger import get_logger
from app.database.session import SessionLocal
from app.entity.db_models import DetectionResult, DetectionScene, DetectionTask, User
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
        summary[item["name"]] = summary.get(item["name"], 0) + item.get(
            "pixel_count", 0
        )
    return summary


class DetectionChatService:
    """Chat-oriented detection inference service."""

    def _infer_one(self, image_source: str | Image.Image) -> dict[str, Any]:
        """Run semantic inference on a single image path or PIL image."""
        if isinstance(image_source, Image.Image):
            image = image_source.convert("RGB")
            result = semantic_model_ops.predict(image, use_pt_fallback=True)
            result["filename"] = "frame.jpg"
            result["image_width"] = image.width
            result["image_height"] = image.height
            return result

        image = _pil_from_path(image_source)
        result = semantic_model_ops.predict(image, use_pt_fallback=True)
        result["filename"] = os.path.basename(image_source)
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
                per_image.append(
                    {
                        "filename": result["filename"],
                        "image_width": result["image_width"],
                        "image_height": result["image_height"],
                        "annotated_image": result.get("annotated_image"),
                        "class_statistics": result.get("class_statistics", []),
                        "inference_time_ms": result.get("inference_time_ms"),
                    }
                )
                total_inference_ms += result.get("inference_time_ms") or 0
                for name, count in _summarize_statistics(
                    result.get("class_statistics", [])
                ).items():
                    aggregated_counts[name] = aggregated_counts.get(name, 0) + count
            except Exception as exc:
                logger.warning("Batch inference failed for %s: %s", path, exc)
                per_image.append(
                    {"filename": os.path.basename(path), "error": str(exc)}
                )

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
            batch_result = self.segment_batch(
                image_files, user_id=user_id, scene_id=scene_id
            )
            batch_result["mode"] = "zip"
            batch_result["zip_filename"] = os.path.basename(zip_path)
            return batch_result
        except zipfile.BadZipFile:
            return {"error": f"无效的 ZIP 文件: {zip_path}"}
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def detect_video(
        self,
        video_path: str,
        conf: float = 0.25,
        iou: float = 0.45,
        frame_sample_rate: int = 5,
        max_frames: int = 50,
        scene_id: int | None = None,
        user_id: int | None = None,
        task_id: int | None = None,
    ) -> dict[str, Any]:
        """Sample key frames from a video and run semantic inference on each."""
        db = SessionLocal()
        task: DetectionTask | None = None
        try:
            if not os.path.exists(video_path):
                return {"error": f"视频文件不存在: {video_path}"}

            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return {"error": f"无法打开视频文件: {video_path}"}

            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration_seconds = total_frames / fps if fps > 0 else 0.0

            if task_id is not None:
                task = (
                    db.query(DetectionTask).filter(DetectionTask.id == task_id).first()
                )
            elif user_id is not None and scene_id is not None:
                user_exists = db.query(User).filter(User.id == user_id).first()
                scene_exists = (
                    db.query(DetectionScene)
                    .filter(DetectionScene.id == scene_id)
                    .first()
                )
                if user_exists and scene_exists:
                    task = DetectionTask(
                        user_id=user_id,
                        scene_id=scene_id,
                        task_type="video",
                        status="processing",
                        total_images=0,
                        conf_threshold=conf,
                        iou_threshold=iou,
                    )
                    db.add(task)
                    db.flush()
                    task_id = task.id
                else:
                    logger.warning(
                        "Skip creating video task for missing user %s or scene %s",
                        user_id,
                        scene_id,
                    )

            if total_frames <= 0:
                cap.release()
                return {"error": "视频没有可读取的帧"}

            requested_frame_limit = max_frames if max_frames > 0 else total_frames
            target_frames = min(total_frames, max(1, requested_frame_limit))
            if frame_sample_rate and frame_sample_rate > 1:
                target_frames = min(
                    target_frames,
                    max(
                        2 if total_frames > 1 else 1,
                        int(total_frames / frame_sample_rate) + 1,
                    ),
                )
            if total_frames > 1 and target_frames < 2:
                target_frames = 2

            if target_frames >= total_frames:
                sample_indices = list(range(total_frames))
            else:
                sample_indices = []
                for idx in range(target_frames):
                    if target_frames == 1:
                        sample_indices.append(0)
                    else:
                        sample_idx = round(
                            idx * (total_frames - 1) / (target_frames - 1)
                        )
                        if not sample_indices or sample_idx != sample_indices[-1]:
                            sample_indices.append(sample_idx)

            if task is not None:
                task.total_images = len(sample_indices)
                db.commit()

            sample_set = set(sample_indices)
            key_frames: list[dict[str, Any]] = []
            frame_summaries: list[dict[str, Any]] = []
            class_counts: dict[str, int] = {}
            total_objects = 0
            total_inference_time = 0.0
            processed_frames = 0
            frame_idx = 0

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if frame_idx not in sample_set:
                    frame_idx += 1
                    continue

                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_frame = Image.fromarray(rgb_frame)
                inference_result = self._infer_one(pil_frame)
                class_statistics = inference_result.get("class_statistics", [])
                frame_class_counts = _summarize_statistics(class_statistics)
                for name, count in frame_class_counts.items():
                    class_counts[name] = class_counts.get(name, 0) + count
                total_objects += sum(
                    item.get("pixel_count", 0) for item in class_statistics
                )

                inference_time = float(inference_result.get("inference_time_ms") or 0.0)
                total_inference_time += inference_time
                processed_frames += 1

                annotated_image_base64 = inference_result.get("annotated_image")
                if not annotated_image_base64 and inference_result.get(
                    "annotated_image_bytes"
                ):
                    annotated_image_base64 = inference_result.get(
                        "annotated_image_bytes"
                    )

                frame_class_details = [
                    {
                        "name": item.get("name"),
                        "display_name": item.get("display_name") or item.get("name"),
                        "pixel_count": int(item.get("pixel_count", 0) or 0),
                        "ratio": round(float(item.get("ratio") or 0.0), 4),
                    }
                    for item in class_statistics
                    if item.get("pixel_count", 0)
                ]
                frame_class_details.sort(
                    key=lambda item: item.get("pixel_count", 0), reverse=True
                )

                dominant_parts = []
                for detail in frame_class_details[:3]:
                    ratio_percent = (detail.get("ratio") or 0.0) * 100
                    dominant_parts.append(
                        f"{detail.get('display_name') or detail.get('name')}: {ratio_percent:.1f}%"
                    )
                analysis_text = (
                    "本帧主要占比：" + "；".join(dominant_parts)
                    if dominant_parts
                    else "本帧未检测到明显类别占比。"
                )

                frame_summaries.append(
                    {
                        "frame_index": frame_idx,
                        "timestamp": round(frame_idx / fps, 2) if fps else 0.0,
                        "analysis_text": analysis_text,
                        "class_ratios": frame_class_details,
                        "dominant_class": frame_class_details[0].get("display_name")
                        if frame_class_details
                        else None,
                    }
                )

                key_frames.append(
                    {
                        "frame_index": frame_idx,
                        "timestamp": round(frame_idx / fps, 2) if fps else 0.0,
                        "annotated_image_base64": annotated_image_base64,
                        "object_count": sum(
                            item.get("pixel_count", 0) for item in class_statistics
                        ),
                        "class_counts": frame_class_counts,
                        "analysis_text": analysis_text,
                        "class_ratios": frame_class_details,
                        "inference_time": round(inference_time, 2),
                    }
                )

                if task is not None:
                    task.total_objects = total_objects
                    task.total_inference_time = total_inference_time
                    db.commit()

                frame_idx += 1

            cap.release()

            if task is not None:
                task.status = "completed"
                task.total_objects = total_objects
                task.total_inference_time = total_inference_time
                task.completed_at = datetime.now()
                db.commit()

            ratio_trend = []
            if frame_summaries:
                class_names = sorted(
                    {
                        detail.get("name")
                        for summary in frame_summaries
                        for detail in summary.get("class_ratios", [])
                        if detail.get("name")
                    }
                )
                for class_name in class_names:
                    values = []
                    display_name = None
                    for summary in frame_summaries:
                        for detail in summary.get("class_ratios", []):
                            if detail.get("name") != class_name:
                                continue
                            values.append(float(detail.get("ratio") or 0.0))
                            display_name = detail.get("display_name") or class_name
                            break
                    ratio_trend.append(
                        {
                            "name": class_name,
                            "display_name": display_name or class_name,
                            "values": values,
                        }
                    )

            return {
                "mode": "video",
                "task_id": task_id,
                "total_frames": total_frames,
                "processed_frames": processed_frames,
                "fps": round(float(fps), 2),
                "duration_seconds": round(duration_seconds, 2),
                "total_objects": total_objects,
                "class_counts": class_counts,
                "key_frames": key_frames,
                "frame_summaries": frame_summaries,
                "ratio_trend": ratio_trend,
                "frame_labels": [
                    f"第 {summary['frame_index'] + 1} 帧" for summary in frame_summaries
                ],
                "total_inference_time": round(total_inference_time, 2),
            }
        except Exception as exc:
            logger.error("视频检测异常: %s", str(exc), exc_info=True)
            if task_id is not None:
                task = (
                    db.query(DetectionTask).filter(DetectionTask.id == task_id).first()
                )
                if task is not None:
                    task.status = "failed"
                    task.error_message = str(exc)
                    db.commit()
            return {"error": f"视频检测失败: {str(exc)}"}
        finally:
            db.close()

    def detect_camera(
        self,
        camera_index: int = 0,
        duration_seconds: int = 10,
        conf: float = 0.25,
        iou: float = 0.45,
        frame_sample_rate: int = 5,
        max_frames: int = 100,
        scene_id: int | None = None,
        user_id: int | None = None,
        task_id: int | None = None,
    ) -> dict[str, Any]:
        """Capture from a camera device, sample frames over duration_seconds, and run per-frame analysis.

        Returns a payload similar to detect_video but capturing live frames from a device index.
        """
        db = SessionLocal()
        task: DetectionTask | None = None
        try:
            cap = cv2.VideoCapture(camera_index)
            if not cap.isOpened():
                return {"error": f"无法打开摄像头设备: index={camera_index}"}

            # Prepare task record if user/scene provided
            if task_id is not None:
                task = (
                    db.query(DetectionTask).filter(DetectionTask.id == task_id).first()
                )
            elif user_id is not None and scene_id is not None:
                user_exists = db.query(User).filter(User.id == user_id).first()
                scene_exists = (
                    db.query(DetectionScene)
                    .filter(DetectionScene.id == scene_id)
                    .first()
                )
                if user_exists and scene_exists:
                    task = DetectionTask(
                        user_id=user_id,
                        scene_id=scene_id,
                        task_type="camera",
                        status="processing",
                        total_images=0,
                        conf_threshold=conf,
                        iou_threshold=iou,
                    )
                    db.add(task)
                    db.flush()
                    task_id = task.id

            # Capture loop: sample frames evenly over duration
            start_ts = time.time()
            end_ts = start_ts + float(duration_seconds)
            collected_indices: list[int] = []
            key_frames: list[dict[str, Any]] = []
            frame_summaries: list[dict[str, Any]] = []
            class_counts: dict[str, int] = {}
            total_objects = 0
            total_inference_time = 0.0
            processed_frames = 0
            frame_idx = 0

            timestamps: list[float] = []
            while time.time() < end_ts and processed_frames < max_frames:
                ret, frame = cap.read()
                if not ret:
                    # short sleep to avoid busy loop if camera temporarily unavailable
                    time.sleep(0.01)
                    continue

                # Decide whether to sample this frame according to sample rate
                if frame_idx % max(1, frame_sample_rate) != 0:
                    frame_idx += 1
                    continue

                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_frame = Image.fromarray(rgb_frame)
                inference_result = self._infer_one(pil_frame)
                class_statistics = inference_result.get("class_statistics", [])
                frame_class_counts = _summarize_statistics(class_statistics)
                for name, count in frame_class_counts.items():
                    class_counts[name] = class_counts.get(name, 0) + count
                total_objects += sum(
                    item.get("pixel_count", 0) for item in class_statistics
                )

                inference_time = float(inference_result.get("inference_time_ms") or 0.0)
                total_inference_time += inference_time

                annotated_image_base64 = inference_result.get("annotated_image")
                if not annotated_image_base64 and inference_result.get(
                    "annotated_image_bytes"
                ):
                    annotated_image_base64 = inference_result.get(
                        "annotated_image_bytes"
                    )

                frame_class_details = [
                    {
                        "name": item.get("name"),
                        "display_name": item.get("display_name") or item.get("name"),
                        "pixel_count": int(item.get("pixel_count", 0) or 0),
                        "ratio": round(float(item.get("ratio") or 0.0), 4),
                    }
                    for item in class_statistics
                    if item.get("pixel_count", 0)
                ]

                dominant_parts = []
                for detail in frame_class_details[:3]:
                    ratio_percent = (detail.get("ratio") or 0.0) * 100
                    dominant_parts.append(
                        f"{detail.get('display_name') or detail.get('name')}: {ratio_percent:.1f}%"
                    )
                analysis_text = (
                    "本帧主要占比：" + "；".join(dominant_parts)
                    if dominant_parts
                    else "本帧未检测到明显类别占比。"
                )

                frame_summaries.append(
                    {
                        "frame_index": frame_idx,
                        "timestamp": round(time.time() - start_ts, 2),
                        "analysis_text": analysis_text,
                        "class_ratios": frame_class_details,
                        "dominant_class": frame_class_details[0].get("display_name")
                        if frame_class_details
                        else None,
                    }
                )

                key_frames.append(
                    {
                        "frame_index": frame_idx,
                        "timestamp": round(time.time() - start_ts, 2),
                        "annotated_image_base64": annotated_image_base64,
                        "object_count": sum(
                            item.get("pixel_count", 0) for item in class_statistics
                        ),
                        "class_counts": frame_class_counts,
                        "analysis_text": analysis_text,
                        "class_ratios": frame_class_details,
                        "inference_time": round(inference_time, 2),
                    }
                )

                processed_frames += 1
                frame_idx += 1

                if task is not None:
                    task.total_objects = total_objects
                    task.total_inference_time = total_inference_time
                    db.commit()

            cap.release()

            # Build ratio trend (total counts across sampled frames)
            ratio_trend = []
            if frame_summaries:
                class_names = sorted(
                    {
                        detail.get("name")
                        for summary in frame_summaries
                        for detail in summary.get("class_ratios", [])
                        if detail.get("name")
                    }
                )
                for class_name in class_names:
                    values = []
                    display_name = None
                    for summary in frame_summaries:
                        for detail in summary.get("class_ratios", []):
                            if detail.get("name") != class_name:
                                continue
                            values.append(float(detail.get("ratio") or 0.0))
                            display_name = detail.get("display_name") or class_name
                            break
                    ratio_trend.append(
                        {
                            "name": class_name,
                            "display_name": display_name or class_name,
                            "values": values,
                        }
                    )

            if task is not None:
                task.status = "completed"
                task.total_objects = total_objects
                task.total_inference_time = total_inference_time
                task.completed_at = datetime.now()
                db.commit()

            return {
                "mode": "camera",
                "task_id": task_id,
                "processed_frames": processed_frames,
                "duration_seconds": duration_seconds,
                "total_objects": total_objects,
                "class_counts": class_counts,
                "key_frames": key_frames,
                "frame_summaries": frame_summaries,
                "ratio_trend": ratio_trend,
                "frame_labels": [
                    f"第 {summary['frame_index'] + 1} 帧" for summary in frame_summaries
                ],
                "total_inference_time": round(total_inference_time, 2),
            }
        except Exception as exc:
            logger.error("摄像头检测异常: %s", str(exc), exc_info=True)
            if task_id is not None:
                task = (
                    db.query(DetectionTask).filter(DetectionTask.id == task_id).first()
                )
                if task is not None:
                    task.status = "failed"
                    task.error_message = str(exc)
                    db.commit()
            return {"error": f"摄像头检测失败: {str(exc)}"}
        finally:
            # ensure camera released and db closed
            try:
                if "cap" in locals() and cap is not None:
                    cap.release()
            except Exception:
                pass
            db.close()


detection_chat_service = DetectionChatService()
