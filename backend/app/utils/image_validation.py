"""Secure streaming upload and Pillow image validation."""

from dataclasses import dataclass
import hashlib
from pathlib import Path
import tempfile

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config.settings import settings
from app.core.exceptions import DomainError


@dataclass
class ValidatedImage:
    temp_path: Path
    image: Image.Image
    width: int
    height: int
    sha256: str
    content_type: str
    canonical_ext: str
    original_filename: str

    def cleanup(self) -> None:
        self.image.close()
        self.temp_path.unlink(missing_ok=True)


async def validate_upload(file: UploadFile) -> ValidatedImage:
    suffix = Path(file.filename or "image").suffix[:16]
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    path = Path(handle.name)
    digest = hashlib.sha256()
    total = 0
    try:
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > settings.SEMANTIC_MAX_UPLOAD_BYTES:
                raise DomainError(413, "FILE_TOO_LARGE", "上传文件超过大小限制")
            digest.update(chunk)
            handle.write(chunk)
        handle.close()
        if total == 0:
            raise DomainError(400, "INVALID_IMAGE", "图像文件为空")
        try:
            source = Image.open(path)
            source.load()
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
            raise DomainError(400, "INVALID_IMAGE", "图像损坏或格式不受支持") from exc
        if getattr(source, "n_frames", 1) != 1:
            source.close()
            raise DomainError(400, "INVALID_IMAGE", "不支持多帧或动画图像")
        if source.format not in {"JPEG", "PNG"}:
            source.close()
            raise DomainError(400, "INVALID_IMAGE", "仅支持 JPEG 和 PNG 图像")
        image = ImageOps.exif_transpose(source).convert("RGB")
        source.close()
        width, height = image.size
        if width <= 0 or height <= 0:
            image.close()
            raise DomainError(400, "INVALID_IMAGE", "图像尺寸无效")
        if width > settings.SEMANTIC_MAX_DIMENSION or height > settings.SEMANTIC_MAX_DIMENSION or width * height > settings.SEMANTIC_MAX_PIXELS:
            image.close()
            raise DomainError(413, "IMAGE_DIMENSIONS_EXCEEDED", "图像尺寸或像素数超过限制")
        content_type, ext = ("image/jpeg", ".jpg") if source.format == "JPEG" else ("image/png", ".png")
        original = Path(file.filename or "image").name.replace("\x00", "")[:255] or "image"
        return ValidatedImage(path, image, width, height, digest.hexdigest(), content_type, ext, original)
    except Exception:
        handle.close()
        path.unlink(missing_ok=True)
        raise
