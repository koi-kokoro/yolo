"""Tests for Day 8 detection chat / agent shortcut endpoints."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.services.detection_chat_service import detection_chat_service


@pytest.fixture()
def authenticated_client(client: TestClient) -> TestClient:
    """Bypass auth for route-level smoke tests."""
    from app.api.auth import get_current_user

    def override():
        class FakeUser:
            id = 1
            username = "test"
            is_superuser = True

        return FakeUser()

    client.app.dependency_overrides[get_current_user] = override
    yield client
    client.app.dependency_overrides.clear()


@pytest.fixture()
def dummy_image(tmp_path: Path) -> str:
    """Create a small RGB image on disk."""
    path = tmp_path / "dummy.png"
    Image.fromarray(np.zeros((64, 64, 3), dtype=np.uint8)).save(path)
    return str(path)


@pytest.fixture()
def dummy_zip(tmp_path: Path, dummy_image: str) -> str:
    """Create a ZIP archive containing the dummy image."""
    zip_path = tmp_path / "images.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(dummy_image, arcname="dummy.png")
    return str(zip_path)


def _fake_predict_result():
    return {
        "annotated_image": "aGVsbG8=",
        "class_statistics": [
            {
                "class_id": 0,
                "name": "background",
                "display_name": "背景",
                "rgb": [0, 0, 0],
                "pixel_count": 1000,
                "ratio": 0.5,
            },
            {
                "class_id": 1,
                "name": "building",
                "display_name": "建筑",
                "rgb": [255, 64, 64],
                "pixel_count": 1000,
                "ratio": 0.5,
            },
        ],
        "inference_time_ms": 42.0,
        "model": "fake",
    }


class TestDetectionChatService:
    def test_segment_single(self, dummy_image: str) -> None:
        with patch(
            "app.services.detection_chat_service.semantic_model_ops.predict",
            return_value=_fake_predict_result(),
        ):
            result = detection_chat_service.segment_single(dummy_image)

        assert result["mode"] == "single"
        assert result["filename"] == "dummy.png"
        assert result["image_width"] == 64
        assert result["image_height"] == 64
        assert "annotated_image" in result
        assert result["class_counts"]["background"] == 1000

    def test_segment_batch(self, dummy_image: str) -> None:
        with patch(
            "app.services.detection_chat_service.semantic_model_ops.predict",
            return_value=_fake_predict_result(),
        ):
            result = detection_chat_service.segment_batch([dummy_image, dummy_image])

        assert result["mode"] == "batch"
        assert result["total_images"] == 2
        assert result["successful_images"] == 2
        assert len(result["annotated_images"]) == 2
        assert result["class_counts"]["background"] == 2000

    def test_segment_zip(self, dummy_zip: str) -> None:
        with patch(
            "app.services.detection_chat_service.semantic_model_ops.predict",
            return_value=_fake_predict_result(),
        ):
            result = detection_chat_service.segment_zip(dummy_zip)

        assert result["mode"] == "zip"
        assert result["zip_filename"] == "images.zip"
        assert result["total_images"] == 1


class TestSegmentationRoutes:
    def test_segment_single_route(self, authenticated_client: TestClient) -> None:
        image_bytes = io.BytesIO()
        Image.fromarray(np.zeros((64, 64, 3), dtype=np.uint8)).save(image_bytes, format="PNG")
        image_bytes.seek(0)

        with patch(
            "app.api.chat.detection_chat_service.segment_single",
            return_value={
                "mode": "single",
                "filename": "test.png",
                "image_width": 64,
                "image_height": 64,
                "annotated_image": "aGVsbG8=",
                "class_statistics": [],
                "class_counts": {},
            },
        ):
            resp = authenticated_client.post(
                "/api/segmentation/single",
                files={"file": ("test.png", image_bytes, "image/png")},
                data={"conf": 0.25},
            )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["mode"] == "single"
        assert data["filename"] == "test.png"

    def test_segment_batch_route(self, authenticated_client: TestClient) -> None:
        image_bytes = io.BytesIO()
        Image.fromarray(np.zeros((64, 64, 3), dtype=np.uint8)).save(image_bytes, format="PNG")
        image_bytes.seek(0)

        with patch(
            "app.api.chat.detection_chat_service.segment_batch",
            return_value={
                "mode": "batch",
                "total_images": 1,
                "successful_images": 1,
                "total_inference_ms": 42.0,
                "class_counts": {},
                "annotated_images": [],
            },
        ):
            resp = authenticated_client.post(
                "/api/segmentation/batch",
                files={"files": ("test.png", image_bytes, "image/png")},
            )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["mode"] == "batch"

    def test_segment_zip_route(self, authenticated_client: TestClient) -> None:
        zip_bytes = io.BytesIO()
        with zipfile.ZipFile(zip_bytes, "w") as zf:
            image_bytes = io.BytesIO()
            Image.fromarray(np.zeros((64, 64, 3), dtype=np.uint8)).save(image_bytes, format="PNG")
            zf.writestr("test.png", image_bytes.getvalue())
        zip_bytes.seek(0)

        with patch(
            "app.api.chat.detection_chat_service.segment_zip",
            return_value={
                "mode": "zip",
                "total_images": 1,
                "successful_images": 1,
                "total_inference_ms": 42.0,
                "class_counts": {},
                "annotated_images": [],
                "zip_filename": "test.zip",
            },
        ):
            resp = authenticated_client.post(
                "/api/segmentation/zip",
                files={"file": ("test.zip", zip_bytes, "application/zip")},
            )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["mode"] == "zip"

    def test_chat_upload(self, authenticated_client: TestClient) -> None:
        image_bytes = io.BytesIO()
        Image.fromarray(np.zeros((64, 64, 3), dtype=np.uint8)).save(image_bytes, format="PNG")
        image_bytes.seek(0)

        resp = authenticated_client.post(
            "/api/chat/upload",
            files={"file": ("test.png", image_bytes, "image/png")},
        )
        assert resp.status_code == 200, resp.text
        assert "image_path" in resp.json()

    def test_chat_stream_validation(self, authenticated_client: TestClient) -> None:
        resp = authenticated_client.post("/api/chat/stream", json={})
        assert resp.status_code == 400


class TestDetectionAgentTools:
    def test_tools_are_callable(self, dummy_image: str) -> None:
        """Ensure the decorated tools can be invoked directly."""
        from app.agent.detection_agent import segment_single_image

        with patch(
            "app.agent.detection_agent.detection_chat_service.segment_single",
            return_value={"mode": "single", "filename": "x.png"},
        ):
            result = segment_single_image.invoke({"image_path": dummy_image})
            parsed = json.loads(result)
            assert parsed["mode"] == "single"
