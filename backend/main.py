"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.model_management import router as model_management_router
from app.api.semantic_models import router as semantic_models_router
from app.api.semantic_tasks import router as semantic_router
from app.config.settings import settings
from app.core.exceptions import register_exception_handlers
from app.core.logger import get_logger, setup_logging
from app.middleware.request_logger import RequestLoggerMiddleware

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
    from app.services.semantic_task_service import semantic_task_service

    logger.info("Initializing services")
    init_minio()
    db = SessionLocal()
    try:
        recovered = semantic_task_service.recover_interrupted(db)
        if recovered:
            logger.warning("Marked %s interrupted semantic tasks as failed", recovered)
    except Exception as exc:
        logger.warning("Semantic recovery skipped: %s", exc)
    finally:
        db.close()
    semantic_runtime.start()
    yield
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
app.include_router(semantic_models_router)
app.include_router(model_management_router)


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
