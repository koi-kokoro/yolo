"""Semantic task persistence, ownership, processing and compensation."""

from datetime import datetime
import math
import time
from uuid import uuid4

from PIL import Image, ImageOps
from sqlalchemy import update
from sqlalchemy.orm import Session, joinedload

from app.config.settings import settings
from app.core.exceptions import DomainError
from app.core.logger import get_logger
from app.database.session import SessionLocal
from app.entity.db_models import (
    DetectionScene,
    ModelVersion,
    SemanticResult,
    SemanticTask,
    DetectionTask,
)
from app.services.semantic_inference import build_artifacts, preprocess
from app.services.semantic_dashboard_metrics import (
    build_semantic_metrics,
    derive_semantic_sample,
)
from app.services.semantic_runtime import semantic_runtime
from app.storage.minio_client import MinIOClient

logger = get_logger(__name__)


class SemanticTaskService:
    def __init__(self, storage_factory=MinIOClient):
        self.storage_factory = storage_factory

    def _default_model(self, db: Session) -> ModelVersion:
        model = (
            db.query(ModelVersion)
            .filter(
                ModelVersion.task_kind == "semantic_segmentation",
                ModelVersion.is_default.is_(True),
                ModelVersion.status == "active",
            )
            .first()
        )
        if not model:
            raise DomainError(503, "MODEL_UNAVAILABLE", "语义分割模型版本未部署")
        return model

    def check_create_allowed(self, db: Session, user_id: int) -> None:
        if not semantic_runtime.ready:
            raise DomainError(503, "MODEL_UNAVAILABLE", "语义分割模型不可用")
        if not semantic_runtime.has_capacity():
            raise DomainError(429, "INFERENCE_QUEUE_FULL", "推理队列已满")
        active = (
            db.query(SemanticTask)
            .filter(
                SemanticTask.user_id == user_id,
                SemanticTask.status.in_(("pending", "running")),
            )
            .count()
        )
        if active >= settings.SEMANTIC_USER_ACTIVE_LIMIT:
            raise DomainError(429, "INFERENCE_QUEUE_FULL", "当前用户活动任务数已达上限")

    def create(self, db: Session, user_id: int, validated) -> SemanticTask:
        self.check_create_allowed(db, user_id)
        model = self._default_model(db)
        task_uuid = str(uuid4())
        key = f"semantic/users/{user_id}/tasks/{task_uuid}/source/original{validated.canonical_ext}"
        storage = self.storage_factory()
        try:
            storage.upload_file(key, str(validated.temp_path), validated.content_type)
        except Exception as exc:
            raise DomainError(500, "STORAGE_ERROR", "原图存储失败") from exc
        task = SemanticTask(
            task_uuid=task_uuid,
            user_id=user_id,
            model_version_id=model.id,
            status="pending",
            original_filename=validated.original_filename,
            source_object_key=key,
            source_sha256=validated.sha256,
            source_content_type=validated.content_type,
            image_width=validated.width,
            image_height=validated.height,
        )
        try:
            db.add(task)
            db.commit()
            db.refresh(task)
        except Exception:
            db.rollback()
            storage.delete_many([key])
            raise
        if not semantic_runtime.submit(self.process, task.id):
            task.status, task.error_code, task.error_message, task.completed_at = (
                "failed",
                "INFERENCE_QUEUE_FULL",
                "任务提交失败，请稍后重试",
                datetime.now(),
            )
            db.commit()
        return task

    def process(self, task_id: int) -> None:
        db = SessionLocal()
        storage = self.storage_factory()
        uploaded: list[str] = []
        started_total = time.perf_counter()
        try:
            claimed = db.execute(
                update(SemanticTask)
                .where(SemanticTask.id == task_id, SemanticTask.status == "pending")
                .values(status="running", started_at=datetime.now())
            ).rowcount
            db.commit()
            if claimed != 1:
                return
            task = (
                db.query(SemanticTask)
                .options(joinedload(SemanticTask.model_version))
                .filter(SemanticTask.id == task_id)
                .one()
            )
            import io

            with Image.open(
                io.BytesIO(storage.read_bytes(task.source_object_key))
            ) as source:
                original = ImageOps.exif_transpose(source).convert("RGB")
            tensor = preprocess(original, semantic_runtime.engine.input_size)
            output, inference_ms = semantic_runtime.engine.infer(tensor)
            artifacts = build_artifacts(
                original,
                output,
                semantic_runtime.engine.metadata["classes"],
                settings.SEMANTIC_OVERLAY_ALPHA,
            )
            prefix = f"semantic/users/{task.user_id}/tasks/{task.task_uuid}/outputs"
            keys = [
                f"{prefix}/index_mask.png",
                f"{prefix}/color_mask.png",
                f"{prefix}/overlay.png",
            ]
            for key, data in zip(
                keys, (artifacts.index_mask, artifacts.color_mask, artifacts.overlay)
            ):
                storage.upload_bytes(key, data, "image/png")
                uploaded.append(key)
            metadata = {
                "engine": semantic_runtime.engine.engine,
                "provider": semantic_runtime.engine.provider,
                "model_name": semantic_runtime.engine.metadata["model"],
                "model_version": semantic_runtime.engine.model_version,
                "model_sha256": semantic_runtime.engine.model_sha256,
                "metadata_sha256": semantic_runtime.engine.metadata_sha256,
                "input_name": semantic_runtime.engine.input_name,
                "output_name": semantic_runtime.engine.output_name,
                "input_size": list(semantic_runtime.engine.input_size),
                "source_size": [task.image_width, task.image_height],
                "resize_mode": "stretch",
                "color_space": "RGB",
                "normalization": "float32_0_1",
                "batch_size": 1,
                "output_shape": artifacts.output_shape,
                "public_class_count": 7,
                "internal_label_7_collapsed": artifacts.internal_label_7_collapsed,
                "runtime_version": semantic_runtime.engine.runtime_version,
                "app_version": settings.APP_VERSION,
            }
            total_ms = round((time.perf_counter() - started_total) * 1000)
            db.add(
                SemanticResult(
                    task_id=task.id,
                    index_mask_object_key=keys[0],
                    color_mask_object_key=keys[1],
                    overlay_object_key=keys[2],
                    class_statistics=artifacts.class_statistics,
                    inference_metadata=metadata,
                    inference_time_ms=inference_ms,
                    total_time_ms=total_ms,
                )
            )
            task.status, task.completed_at = "succeeded", datetime.now()
            db.commit()

            # Mirror a lightweight detection history entry so the UI history/dashboard
            # (which reads from DetectionTask) can surface semantic tasks.
            try:
                # compute a sensible total_objects: number of classes with non-zero pixels
                total_objects = sum(
                    1
                    for item in artifacts.class_statistics
                    if item.get("pixel_count", 0) > 0
                )
                scene_id = (
                    task.model_version.scene_id
                    if task.model_version is not None
                    else None
                )
                if scene_id is None:
                    # cannot mirror without a scene_id (DetectionTask.scene_id non-nullable)
                    raise RuntimeError(
                        "No scene_id available to mirror semantic task to detection history"
                    )
                detection_task = DetectionTask(
                    user_id=task.user_id,
                    scene_id=scene_id,
                    model_version_id=task.model_version_id,
                    task_type="semantic",
                    status="completed",
                    total_images=1,
                    total_objects=total_objects,
                    semantic_metrics=build_semantic_metrics(
                        [
                            derive_semantic_sample(
                                artifacts.class_statistics,
                                task.original_filename,
                            )
                        ]
                    ),
                    total_inference_time=total_ms,
                    conf_threshold=0.0,
                    iou_threshold=0.0,
                    created_at=task.created_at,
                    completed_at=task.completed_at,
                )
                db.add(detection_task)
                db.commit()
            except Exception:
                # keep semantic task success even if mirroring fails; log and continue
                db.rollback()
        except Exception as exc:
            db.rollback()
            storage.delete_many(uploaded)
            task = db.query(SemanticTask).filter(SemanticTask.id == task_id).first()
            if task and task.status not in ("succeeded", "failed"):
                task.status, task.error_code, task.error_message, task.completed_at = (
                    "failed",
                    "INFERENCE_FAILED",
                    "语义分割处理失败",
                    datetime.now(),
                )
                db.commit()
            logger.exception("Semantic task %s failed: %s", task_id, exc)
        finally:
            db.close()

    def get_owned(self, db: Session, task_uuid: str, user_id: int) -> SemanticTask:
        task = (
            db.query(SemanticTask)
            .options(
                joinedload(SemanticTask.model_version), joinedload(SemanticTask.result)
            )
            .filter(
                SemanticTask.task_uuid == task_uuid, SemanticTask.user_id == user_id
            )
            .first()
        )
        if not task:
            raise DomainError(404, "SEMANTIC_TASK_NOT_FOUND", "任务不存在")
        return task

    def list_owned(
        self, db: Session, user_id: int, page: int, page_size: int, status: str | None
    ):
        query = (
            db.query(SemanticTask)
            .options(
                joinedload(SemanticTask.model_version), joinedload(SemanticTask.result)
            )
            .filter(SemanticTask.user_id == user_id)
        )
        if status:
            if status not in {"pending", "running", "succeeded", "failed"}:
                raise DomainError(422, "VALIDATION_ERROR", "任务状态无效")
            query = query.filter(SemanticTask.status == status)
        total = query.count()
        items = (
            query.order_by(SemanticTask.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return total, math.ceil(total / page_size) if total else 0, items

    @staticmethod
    def recover_interrupted(db: Session) -> int:
        count = (
            db.query(SemanticTask)
            .filter(SemanticTask.status.in_(("pending", "running")))
            .update(
                {
                    "status": "failed",
                    "error_code": "SERVICE_RESTARTED",
                    "error_message": "服务已重启，请重新创建任务",
                    "completed_at": datetime.now(),
                },
                synchronize_session=False,
            )
        )
        db.commit()
        return count


semantic_task_service = SemanticTaskService()
