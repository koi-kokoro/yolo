"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.config.settings import settings


def init_minio() -> None:
    """Initialize the configured MinIO bucket if MinIO is available."""

    from app.storage.minio_client import MinIOClient

    try:
        minio_client = MinIOClient()
        print(f"MinIO 存储桶 '{minio_client.bucket_name}' 初始化完成")
    except Exception as exc:
        print(f"MinIO 初始化失败: {exc}")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Application startup and shutdown hooks."""

    print("正在初始化服务...")
    init_minio()
    yield
    print("服务已关闭")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="基于 YOLOv11 的目标检测智能体平台 API",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "message": "欢迎使用 RSOD Agent Platform",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


@app.get("/api/health/database")
def database_health() -> dict[str, str]:
    return {
        "status": "configured",
        "database": "postgresql",
        "host": settings.DB_HOST,
        "database_name": settings.DB_NAME,
    }


@app.get("/api/health/redis")
def redis_health() -> dict[str, str]:
    return {
        "status": "configured",
        "redis": settings.REDIS_URL,
    }


@app.get("/api/health/minio")
def minio_health() -> dict[str, str]:
    return {
        "status": "configured",
        "minio": settings.MINIO_ENDPOINT,
        "bucket": settings.MINIO_BUCKET,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
