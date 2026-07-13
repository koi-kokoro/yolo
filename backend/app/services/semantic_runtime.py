"""Bounded single-process semantic inference runtime."""

from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore, Lock
from typing import Callable

from app.config.settings import settings
from app.core.logger import get_logger
from app.services.onnx_semantic_engine import OnnxSemanticEngine

logger = get_logger(__name__)


class SemanticRuntime:
    def __init__(self) -> None:
        self.executor: ThreadPoolExecutor | None = None
        self.engine = None
        self.ready = False
        self.error: str | None = None
        self._slots = BoundedSemaphore(settings.SEMANTIC_EXECUTOR_WORKERS + settings.SEMANTIC_QUEUE_SIZE)
        self._lock = Lock()

    def start(self) -> None:
        with self._lock:
            if self.executor is not None:
                return
            self.executor = ThreadPoolExecutor(max_workers=settings.SEMANTIC_EXECUTOR_WORKERS, thread_name_prefix="semantic")
            try:
                if settings.SEMANTIC_ENGINE.lower() != "onnx":
                    raise RuntimeError("PT runtime is not enabled in this CPU-first backend build")
                self.engine = OnnxSemanticEngine(settings.semantic_deploy_path, settings.SEMANTIC_ONNX_SHA256, settings.SEMANTIC_VERIFY_SHA256)
                self.ready = True
                self.error = None
            except Exception as exc:
                self.ready = False
                self.error = "模型初始化或契约校验失败"
                logger.exception("Semantic runtime unavailable: %s", exc)

    def has_capacity(self) -> bool:
        acquired = self._slots.acquire(blocking=False)
        if acquired:
            self._slots.release()
        return acquired

    def submit(self, job: Callable, *args) -> bool:
        if not self.ready or self.executor is None or not self._slots.acquire(blocking=False):
            return False
        future = self.executor.submit(job, *args)
        future.add_done_callback(lambda _future: self._slots.release())
        return True

    def model_info(self) -> dict:
        if not self.ready or self.engine is None:
            return {"ready": False, "classes": [], "message": self.error or "模型不可用"}
        return {"ready": True, "engine": self.engine.engine, "provider": self.engine.provider, "model_name": self.engine.metadata["model"], "model_version": self.engine.model_version, "input_size": list(self.engine.input_size), "classes": self.engine.metadata["classes"]}

    def shutdown(self) -> None:
        if self.executor:
            self.executor.shutdown(wait=True, cancel_futures=False)
        self.executor = None
        self.ready = False


semantic_runtime = SemanticRuntime()
