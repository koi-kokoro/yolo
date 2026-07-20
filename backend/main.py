"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.model_management import router as model_management_router
from app.api.semantic_models import router as semantic_models_router
from app.api.semantic_tasks import router as semantic_router
from app.api.chat import router as chat_router, segmentation_router
from app.api.training import router as training_router
from app.config.settings import settings
from app.core.exceptions import register_exception_handlers
from app.core.logger import get_logger, setup_logging
from app.middleware.request_logger import RequestLoggerMiddleware
from app.api.dashboard import router as dashboard_router
from app.api.detection import router as detection_router
from app.api.history import router as history_router
from app.api.user import router as user_router

setup_logging()
logger = get_logger(__name__)


def init_minio() -> None:
    """Initialize the configured MinIO bucket if MinIO is available."""

    from app.storage.minio_client import MinIOClient

    try:
        minio_client = MinIOClient()
        logger.info("MinIO bucket '%s' initialized", minio_client.bucket_name)
    except Exception as exc:
        logger.warning("MinIO initialization failed: %s", exc)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Application startup and shutdown hooks."""

    from app.database.session import SessionLocal
    from app.services.semantic_runtime import semantic_runtime
    from app.services.dior_detection_runtime import dior_detection_runtime
    from app.services.semantic_task_service import semantic_task_service
    from app.training.training_service import training_service

    logger.info("Initializing services")
    init_minio()
    db = SessionLocal()
    try:
        try:
            recovered = semantic_task_service.recover_interrupted(db)
            if recovered:
                logger.warning(
                    "Marked %s interrupted semantic tasks as failed", recovered
                )
        except Exception as exc:
            logger.warning("Semantic recovery skipped: %s", exc)
            db.rollback()
        try:
            recovered_training = training_service.recover_active(db)
            if recovered_training:
                logger.warning(
                    "Marked %s online training tasks as interrupted", recovered_training
                )
        except Exception as exc:
            logger.warning("Online training recovery skipped: %s", exc)
            db.rollback()
    finally:
        db.close()
    semantic_runtime.start()
    dior_detection_runtime.start()
    yield
    dior_detection_runtime.shutdown()
    semantic_runtime.shutdown()
    logger.info("Service shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="基于 YOLOv11 的目标检测智能体平台 API",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(RequestLoggerMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_exception_handlers(app)

app.include_router(auth_router)
app.include_router(health_router)
app.include_router(semantic_router)
app.include_router(detection_router)
app.include_router(semantic_models_router)
app.include_router(model_management_router)
app.include_router(chat_router)
app.include_router(segmentation_router)
app.include_router(training_router)
app.include_router(dashboard_router)
app.include_router(history_router)
app.include_router(user_router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "message": "欢迎使用 RSOD Agent Platform",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "redoc": "/redoc",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
