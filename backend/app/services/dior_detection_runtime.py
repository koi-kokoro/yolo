"""Bounded process-local runtime for DIOR detection inference."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import threading
from typing import Any

from PIL import Image

from app.config.settings import settings
from app.core.exceptions import DomainError
from app.core.logger import get_logger
from app.services.dior_detection_engine import DiorDetectionEngine

logger = get_logger(__name__)


def _predict_and_close(engine, image: Image.Image, conf: float, iou: float, image_size: int):
    try:
        return engine.predict(image, conf, iou, image_size)
    finally:
        image.close()


class DiorDetectionRuntime:
    def __init__(self) -> None:
        self.engine: DiorDetectionEngine | None = None
        self.executor: ThreadPoolExecutor | None = None
        self._slots: threading.BoundedSemaphore | None = None
        self.error: str | None = None

    @property
    def ready(self) -> bool:
        return self.engine is not None and self.executor is not None

    def start(self) -> None:
        if self.ready:
            return
        try:
            self.engine = DiorDetectionEngine(
                settings.dior_deploy_path,
                settings.DIOR_DEVICE,
                settings.DIOR_MODEL_SHA256,
                settings.DIOR_VERIFY_SHA256,
            )
            self.executor = ThreadPoolExecutor(
                max_workers=settings.DIOR_EXECUTOR_WORKERS,
                thread_name_prefix="dior-detection",
            )
            self._slots = threading.BoundedSemaphore(
                settings.DIOR_EXECUTOR_WORKERS + settings.DIOR_QUEUE_SIZE
            )
            self.error = None
            logger.info("DIOR detection runtime ready: %s", settings.dior_deploy_path)
        except Exception as exc:
            self.engine = None
            self.error = str(exc)
            logger.warning("DIOR detection runtime unavailable: %s", exc)

    def shutdown(self) -> None:
        if self.executor is not None:
            self.executor.shutdown(wait=True, cancel_futures=True)
        self.executor = None
        self.engine = None
        self._slots = None

    def predict(self, image: Image.Image, conf: float, iou: float, image_size: int) -> dict[str, Any]:
        if not self.ready or self.engine is None or self.executor is None or self._slots is None:
            raise DomainError(503, "DIOR_MODEL_UNAVAILABLE", self.error or "DIOR 检测模型尚未就绪")
        if not self._slots.acquire(blocking=False):
            raise DomainError(429, "DIOR_QUEUE_FULL", "DIOR 检测队列已满，请稍后重试")
        try:
            image_copy = image.copy()
            return self.executor.submit(
                _predict_and_close, self.engine, image_copy, conf, iou, image_size
            ).result()
        finally:
            self._slots.release()

    def model_info(self) -> dict[str, Any]:
        if not self.ready or self.engine is None:
            return {"ready": False, "message": self.error or "DIOR 检测模型尚未就绪"}
        return {
            "ready": True,
            "model": self.engine.metadata["model"],
            "version": self.engine.metadata["version"],
            "task": "detection",
            "engine": self.engine.engine,
            "device": self.engine.device,
            "input_size": self.engine.metadata["input_size"],
            "classes": [
                {"id": index, "name": name}
                for index, name in enumerate(self.engine.metadata["classes"])
            ],
            "metrics": self.engine.metrics,
            "model_sha256": self.engine.model_sha256,
        }


dior_detection_runtime = DiorDetectionRuntime()
