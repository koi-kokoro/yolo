"""Health check API routes."""

from datetime import datetime

from fastapi import APIRouter
from minio import Minio
from redis import Redis
from sqlalchemy import text

from app.config.settings import settings
from app.core.logger import get_logger
from app.database.session import SessionLocal

logger = get_logger(__name__)
router = APIRouter(prefix="/api/health", tags=["健康检查"])


def _check_postgresql() -> dict:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return {"status": "healthy", "message": "PostgreSQL 连接正常"}
    except Exception as exc:
        logger.warning("PostgreSQL health check failed: %s", exc)
        return {"status": "unhealthy", "message": "PostgreSQL 连接失败"}


def _check_redis() -> dict:
    try:
        client = Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
        client.ping()
        client.close()
        return {"status": "healthy", "message": "Redis 连接正常"}
    except Exception as exc:
        logger.warning("Redis health check failed: %s", exc)
        return {"status": "unhealthy", "message": "Redis 连接失败"}


def _check_minio() -> dict:
    try:
        client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        client.bucket_exists(settings.MINIO_BUCKET)
        return {"status": "healthy", "message": "MinIO 连接正常"}
    except Exception as exc:
        logger.warning("MinIO health check failed: %s", exc)
        return {"status": "unhealthy", "message": "MinIO 连接失败"}


@router.get("")
def health_check() -> dict:
    """Return basic application health."""

    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/detail")
def health_detail() -> dict:
    """Return detailed dependency health without raising dependency errors."""

    dependencies = {
        "postgresql": _check_postgresql(),
        "redis": _check_redis(),
        "minio": _check_minio(),
    }
    failed = [name for name, result in dependencies.items() if result["status"] != "healthy"]

    if not failed:
        status = "healthy"
    elif len(failed) == len(dependencies):
        status = "unhealthy"
    else:
        status = "degraded"

    return {
        "status": status,
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "timestamp": datetime.utcnow().isoformat(),
        "dependencies": dependencies,
    }
