"""MinIO object storage client wrapper."""

import io
from datetime import timedelta
from pathlib import Path

from minio import Minio
from minio.error import S3Error

from app.config.settings import settings


class MinIOClient:
    """Thin wrapper around the MinIO SDK used by the backend."""

    def __init__(self) -> None:
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        self.bucket_name = settings.MINIO_BUCKET
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        """Ensure the configured bucket exists."""

        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
        except S3Error as exc:
            print(f"MinIO bucket 初始化警告: {exc}")

    def upload_file(self, object_name: str, file_path: str, content_type: str | None = None) -> str:
        """Upload a local file and return its stable object key."""

        self.client.fput_object(
            bucket_name=self.bucket_name,
            object_name=object_name,
            file_path=file_path,
            content_type=content_type,
        )
        return object_name

    def upload_bytes(self, object_name: str, data: bytes, content_type: str = "image/jpeg") -> str:
        """Upload bytes and return its stable object key."""

        self.client.put_object(
            bucket_name=self.bucket_name,
            object_name=object_name,
            data=io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return object_name

    def read_bytes(self, object_name: str) -> bytes:
        response = self.client.get_object(self.bucket_name, object_name)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def exists(self, object_name: str) -> bool:
        try:
            self.client.stat_object(self.bucket_name, object_name)
            return True
        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
                return False
            raise

    def get_presigned_url(self, object_name: str, expires_seconds: int | None = None) -> str:
        """Return a short-lived presigned GET URL for an object."""

        return self.client.presigned_get_object(
            bucket_name=self.bucket_name,
            object_name=object_name,
            expires=timedelta(seconds=expires_seconds or settings.SEMANTIC_URL_EXPIRE_SECONDS),
        )

    def delete_file(self, object_name: str) -> None:
        """Delete an object from MinIO."""

        self.client.remove_object(bucket_name=self.bucket_name, object_name=object_name)

    def delete_many(self, object_names: list[str]) -> None:
        for object_name in object_names:
            try:
                self.delete_file(object_name)
            except Exception:
                pass
