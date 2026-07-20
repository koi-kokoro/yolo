"""用户隔离的聊天图片引用；对外只暴露不可猜测 token。"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import BinaryIO

from app.config.settings import settings

_REFERENCE_RE = re.compile(r"^[0-9a-f]{32}$")
_ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


class ChatImageReferenceService:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or settings.chat_upload_path).resolve()

    def _user_dir(self, user_id: int, *, create: bool = False) -> Path:
        directory = (self.root / str(int(user_id))).resolve()
        if directory.parent != self.root:
            raise ValueError("无效用户图片目录")
        if create:
            directory.mkdir(parents=True, exist_ok=True)
        return directory

    def save(self, user_id: int, filename: str | None, stream: BinaryIO) -> str:
        suffix = Path(filename or "").suffix.lower()
        if suffix not in _ALLOWED_SUFFIXES:
            raise ValueError("不支持的图片扩展名")
        reference = uuid.uuid4().hex
        path = self._user_dir(user_id, create=True) / f"{reference}{suffix}"
        with path.open("xb") as handle:
            handle.write(stream.read())
        return reference

    def resolve(self, user_id: int, reference: str) -> Path:
        normalized = str(reference).strip().lower()
        if not _REFERENCE_RE.fullmatch(normalized):
            raise FileNotFoundError(reference)
        user_dir = self._user_dir(user_id)
        for suffix in _ALLOWED_SUFFIXES:
            candidate = (user_dir / f"{normalized}{suffix}").resolve()
            if candidate.parent == user_dir and candidate.is_file():
                return candidate
        raise FileNotFoundError(reference)

    def reference_for_path(self, user_id: int, value: str) -> str:
        """兼容旧调用，但只接受当前用户目录中的可信路径。"""
        resolved = Path(value).resolve(strict=False)
        user_dir = self._user_dir(user_id)
        if resolved.parent != user_dir or not resolved.is_file():
            raise FileNotFoundError(value)
        reference = resolved.stem.lower()
        if not _REFERENCE_RE.fullmatch(reference) or resolved.suffix.lower() not in _ALLOWED_SUFFIXES:
            raise FileNotFoundError(value)
        return reference


chat_image_reference_service = ChatImageReferenceService()
