"""DIOR facility-detection application service and persistence boundary."""

from __future__ import annotations

import uuid
import hashlib
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.exceptions import DomainError
from app.core.logger import get_logger
from app.entity.db_models import DetectionResult, DetectionScene, DetectionTask, ModelVersion
from app.services.dior_detection_runtime import dior_detection_runtime
from app.storage.minio_client import MinIOClient
from app.utils.image_validation import ValidatedImage
from PIL import Image, ImageOps

logger = get_logger(__name__)

DIOR_CLASS_NAMES_CN = {
    "airplane": "飞机",
    "airport": "机场",
    "baseballfield": "棒球场",
    "basketballcourt": "篮球场",
    "bridge": "桥梁",
    "chimney": "烟囱",
    "dam": "水坝",
    "Expressway-Service-area": "高速公路服务区",
    "Expressway-toll-station": "高速公路收费站",
    "golffield": "高尔夫球场",
    "groundtrackfield": "田径场",
    "harbor": "港口",
    "overpass": "立交桥",
    "ship": "船舶",
    "stadium": "体育场",
    "storagetank": "储油罐",
    "tenniscourt": "网球场",
    "trainstation": "火车站",
    "vehicle": "车辆",
    "windmill": "风力发电机",
}


class FacilityDetectionService:
    SCENE_NAME = "dior_facility_detection"

    def __init__(self) -> None:
        self.runtime = dior_detection_runtime
        self._storage: MinIOClient | None = None

    def _storage_client(self) -> MinIOClient:
        if self._storage is None:
            self._storage = MinIOClient()
        return self._storage

    def model_info(self) -> dict[str, Any]:
        info = self.runtime.model_info()
        if info.get("ready"):
            info["display_name"] = "DIOR 遥感设施目标检测"
            for item in info["classes"]:
                item["display_name"] = DIOR_CLASS_NAMES_CN.get(item["name"], item["name"])
        return info

    def ensure_registry(self, db: Session) -> tuple[DetectionScene, ModelVersion]:
        metadata = self.runtime.engine.metadata if self.runtime.engine is not None else {
            "classes": list(DIOR_CLASS_NAMES_CN),
            "version": "20260713-102958",
            "model": "dior-yolo11n",
            "input_size": settings.DIOR_INPUT_SIZE,
        }
        scene = db.query(DetectionScene).filter(DetectionScene.name == self.SCENE_NAME).first()
        if scene is None:
            scene = DetectionScene(
                name=self.SCENE_NAME,
                display_name="DIOR 遥感设施检测",
                description="DIOR 20 类遥感目标水平框检测",
                category="object_detection",
                class_names=metadata["classes"],
                class_names_cn=DIOR_CLASS_NAMES_CN,
                is_active=True,
            )
            db.add(scene)
            db.flush()

        version = (
            db.query(ModelVersion)
            .filter(
                ModelVersion.scene_id == scene.id,
                ModelVersion.version == metadata["version"],
                ModelVersion.task_kind == "detection",
            )
            .first()
        )
        if version is None:
            db.query(ModelVersion).filter(
                ModelVersion.scene_id == scene.id,
                ModelVersion.task_kind == "detection",
            ).update({ModelVersion.is_default: False}, synchronize_session=False)
            metrics = self.runtime.engine.metrics if self.runtime.engine is not None else {}
            model_path = settings.dior_deploy_path / "best.pt"
            version = ModelVersion(
                scene_id=scene.id,
                version=metadata["version"],
                model_name=metadata["model"],
                model_type="yolo11n",
                status="active",
                model_path=str(model_path),
                map50=metrics.get("map50"),
                map50_95=metrics.get("map50_95"),
                precision=metrics.get("precision"),
                recall=metrics.get("recall"),
                description="DIOR 20 类遥感设施检测部署模型",
                file_size=model_path.stat().st_size if model_path.is_file() else None,
                is_default=True,
                task_kind="detection",
                runtime="ultralytics-pt",
                artifact_sha256=(
                    self.runtime.engine.model_sha256 if self.runtime.engine is not None else None
                ),
                model_metadata=metadata,
            )
            db.add(version)
            db.flush()
        db.commit()
        db.refresh(scene)
        db.refresh(version)
        return scene, version

    def detect(
        self,
        db: Session,
        user_id: int,
        images: list[ValidatedImage],
        conf: float,
        iou: float,
        image_size: int,
        include_object_keys: bool = False,
    ) -> dict[str, Any]:
        if not self.runtime.ready:
            raise DomainError(
                503,
                "DIOR_MODEL_UNAVAILABLE",
                getattr(self.runtime, "error", None) or "DIOR 检测模型尚未就绪",
            )
        scene, version = self.ensure_registry(db)
        task = DetectionTask(
            user_id=user_id,
            scene_id=scene.id,
            model_version_id=version.id,
            task_type="single" if len(images) == 1 else "batch",
            status="processing",
            total_images=len(images),
            total_objects=0,
            total_inference_time=0.0,
            conf_threshold=conf,
            iou_threshold=iou,
            image_size=image_size,
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        storage = self._storage_client()
        response_images: list[dict[str, Any]] = []
        total_objects = 0
        total_inference_ms = 0.0
        aggregate = Counter()
        stored_keys: list[str] = []
        try:
            for image_index, validated in enumerate(images):
                prediction = self.runtime.predict(validated.image, conf, iou, image_size)
                token = uuid.uuid4().hex
                prefix = f"detection/users/{user_id}/tasks/{task.id}/{image_index:04d}-{token}"
                source_key = f"{prefix}/source{validated.canonical_ext}"
                annotated_key = f"{prefix}/annotated.jpg"
                storage.upload_file(source_key, str(validated.temp_path), validated.content_type)
                stored_keys.append(source_key)
                storage.upload_bytes(annotated_key, prediction["annotated_jpeg"], "image/jpeg")
                stored_keys.append(annotated_key)

                detections = []
                for item in prediction["detections"]:
                    class_name = item["class_name"]
                    class_name_cn = DIOR_CLASS_NAMES_CN.get(class_name, class_name)
                    record = DetectionResult(
                        task_id=task.id,
                        image_path=source_key,
                        annotated_image_url=annotated_key,
                        class_name=class_name,
                        class_name_cn=class_name_cn,
                        class_id=item["class_id"],
                        confidence=item["confidence"],
                        bbox=item["bbox"],
                        inference_time=prediction["inference_time_ms"],
                        image_width=validated.width,
                        image_height=validated.height,
                    )
                    db.add(record)
                    enriched = dict(item)
                    enriched["class_name_cn"] = class_name_cn
                    detections.append(enriched)
                    aggregate[class_name] += 1

                image_count = len(detections)
                total_objects += image_count
                total_inference_ms += float(prediction["inference_time_ms"])
                response_image = {
                    "filename": validated.original_filename,
                    "width": validated.width,
                    "height": validated.height,
                    "total_objects": image_count,
                    "inference_time_ms": prediction["inference_time_ms"],
                    "source_url": storage.get_presigned_url(source_key),
                    "annotated_image_url": storage.get_presigned_url(annotated_key),
                    "detections": detections,
                }
                if include_object_keys:
                    response_image["source_object_key"] = source_key
                    response_image["annotated_object_key"] = annotated_key
                response_images.append(response_image)

            task.status = "completed"
            task.total_objects = total_objects
            task.total_inference_time = round(total_inference_ms, 2)
            task.completed_at = datetime.now()
            db.commit()
        except Exception as exc:
            db.rollback()
            if stored_keys:
                try:
                    storage.delete_many(stored_keys)
                except Exception:
                    logger.warning("Could not remove partial DIOR task objects", exc_info=True)
            failed_task = db.query(DetectionTask).filter(DetectionTask.id == task.id).first()
            if failed_task is not None:
                failed_task.status = "failed"
                failed_task.error_message = str(exc)[:1000]
                failed_task.completed_at = datetime.now()
                db.commit()
            logger.exception("DIOR detection task %s failed", task.id)
            raise

        class_statistics = [
            {
                "class_name": name,
                "class_name_cn": DIOR_CLASS_NAMES_CN.get(name, name),
                "count": count,
            }
            for name, count in aggregate.most_common()
        ]
        return {
            "task_id": task.id,
            "mode": task.task_type,
            "model": {
                "name": version.model_name,
                "version": version.version,
                "engine": version.runtime,
            },
            "total_images": len(images),
            "total_objects": total_objects,
            "total_inference_ms": round(total_inference_ms, 2),
            "class_statistics": class_statistics,
            "images": response_images,
        }

    def detect_local_file(
        self,
        db: Session,
        user_id: int,
        image_path: str,
        conf: float | None = None,
        iou: float | None = None,
        image_size: int | None = None,
        include_object_keys: bool = False,
    ) -> dict[str, Any]:
        """Run the same persisted pipeline for a trusted chat-upload path."""
        path = Path(image_path).resolve()
        with Image.open(path) as source:
            source.load()
            source_format = source.format
            image = ImageOps.exif_transpose(source).convert("RGB")
        if source_format not in {"JPEG", "PNG"}:
            image.close()
            raise ValueError("DIOR chat detection only supports JPEG and PNG")
        raw = path.read_bytes()
        validated = ValidatedImage(
            temp_path=path,
            image=image,
            width=image.width,
            height=image.height,
            sha256=hashlib.sha256(raw).hexdigest(),
            content_type="image/jpeg" if source_format == "JPEG" else "image/png",
            canonical_ext=".jpg" if source_format == "JPEG" else ".png",
            original_filename=path.name,
        )
        try:
            return self.detect(
                db,
                user_id,
                [validated],
                conf if conf is not None else settings.DIOR_CONF_THRESHOLD,
                iou if iou is not None else settings.DIOR_IOU_THRESHOLD,
                image_size if image_size is not None else settings.DIOR_INPUT_SIZE,
                include_object_keys=include_object_keys,
            )
        finally:
            image.close()


facility_detection_service = FacilityDetectionService()
