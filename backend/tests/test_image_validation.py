"""Upload validation tests."""

import io

from fastapi import UploadFile
from PIL import Image
import pytest

from app.core.exceptions import DomainError
from app.utils.image_validation import validate_upload


def image_bytes(fmt="PNG", size=(8, 6)):
    stream = io.BytesIO()
    Image.new("RGB", size, (1, 2, 3)).save(stream, format=fmt)
    return stream.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize(("fmt", "name", "mime", "ext"), [("PNG", "fake.jpg", "image/png", ".png"), ("JPEG", "fake.png", "image/jpeg", ".jpg")])
async def test_magic_decode_controls_format_and_temp_cleanup(fmt, name, mime, ext):
    validated = await validate_upload(UploadFile(filename=name, file=io.BytesIO(image_bytes(fmt))))
    path = validated.temp_path
    assert validated.content_type == mime
    assert validated.canonical_ext == ext
    assert validated.image.size == (8, 6)
    validated.cleanup()
    assert not path.exists()


@pytest.mark.asyncio
async def test_corrupt_image_rejected_and_temp_removed(monkeypatch):
    with pytest.raises(DomainError) as exc:
        await validate_upload(UploadFile(filename="broken.png", file=io.BytesIO(b"not-image")))
    assert exc.value.code == "INVALID_IMAGE"


@pytest.mark.asyncio
async def test_multiframe_rejected():
    stream = io.BytesIO()
    frames = [Image.new("RGB", (2, 2), "red"), Image.new("RGB", (2, 2), "blue")]
    frames[0].save(stream, format="GIF", save_all=True, append_images=frames[1:])
    with pytest.raises(DomainError) as exc:
        await validate_upload(UploadFile(filename="animated.gif", file=io.BytesIO(stream.getvalue())))
    assert exc.value.code == "INVALID_IMAGE"
