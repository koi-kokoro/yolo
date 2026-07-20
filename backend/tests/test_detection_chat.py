"""Tests for Day 8 detection chat / agent shortcut endpoints."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

import cv2
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


@pytest.fixture()
def dummy_video(tmp_path: Path) -> str:
    """Create a tiny MP4 video file for video-detection tests."""
    video_path = tmp_path / "dummy.mp4"
    writer = cv2.VideoWriter(
        str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), 5.0, (16, 16)
    )
    for _ in range(4):
        frame = np.zeros((16, 16, 3), dtype=np.uint8)
        writer.write(frame)
    writer.release()
    return str(video_path)


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

    def test_detect_video(self, dummy_video: str) -> None:
        with patch(
            "app.services.detection_chat_service.semantic_model_ops.predict",
            return_value=_fake_predict_result(),
        ):
            result = detection_chat_service.detect_video(
                dummy_video, frame_sample_rate=2, max_frames=3
            )

        assert result["mode"] == "video"
        assert result["total_frames"] >= 1
        assert result["processed_frames"] >= 1
        assert result["class_counts"]["background"] >= 1000

    def test_detect_video_samples_multiple_frames_for_short_video(
        self, dummy_video: str
    ) -> None:
        with patch(
            "app.services.detection_chat_service.semantic_model_ops.predict",
            return_value=_fake_predict_result(),
        ):
            result = detection_chat_service.detect_video(
                dummy_video, frame_sample_rate=10, max_frames=10
            )

        assert result["mode"] == "video"
        assert result["processed_frames"] >= 2
        assert len(result["key_frames"]) >= 2

    def test_detect_video_returns_frame_level_analysis(self, dummy_video: str) -> None:
        with patch(
            "app.services.detection_chat_service.semantic_model_ops.predict",
            return_value=_fake_predict_result(),
        ):
            result = detection_chat_service.detect_video(
                dummy_video, frame_sample_rate=10, max_frames=10
            )

        assert result["mode"] == "video"
        assert isinstance(result.get("frame_summaries"), list)
        assert len(result["frame_summaries"]) >= 2
        first_summary = result["frame_summaries"][0]
        assert "analysis_text" in first_summary
        assert "class_ratios" in first_summary
        assert isinstance(result.get("ratio_trend"), list)

    def test_detect_camera_snapshot_mode(self, dummy_video: str) -> None:
        """Use a video file as a surrogate camera input and ensure camera sampling returns expected fields."""
        with patch(
            "app.services.detection_chat_service.semantic_model_ops.predict",
            return_value=_fake_predict_result(),
        ):
            # pass the file path as the camera_index parameter (cv2 accepts paths)
            result = detection_chat_service.detect_camera(
                camera_index=dummy_video,
                duration_seconds=1,
                frame_sample_rate=1,
                max_frames=3,
            )

        assert result["mode"] == "camera"
        assert result["processed_frames"] >= 1
        assert isinstance(result.get("frame_summaries"), list)
        assert isinstance(result.get("key_frames"), list)
        assert result["class_counts"]["background"] >= 1000


class TestSegmentationRoutes:
    def test_segment_single_route(self, authenticated_client: TestClient) -> None:
        image_bytes = io.BytesIO()
        Image.fromarray(np.zeros((64, 64, 3), dtype=np.uint8)).save(
            image_bytes, format="PNG"
        )
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
        Image.fromarray(np.zeros((64, 64, 3), dtype=np.uint8)).save(
            image_bytes, format="PNG"
        )
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
            Image.fromarray(np.zeros((64, 64, 3), dtype=np.uint8)).save(
                image_bytes, format="PNG"
            )
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

    def test_video_route(self, authenticated_client: TestClient) -> None:
        video_bytes = io.BytesIO(b"fake-video")

        with patch(
            "app.api.chat.detection_chat_service.detect_video",
            return_value={
                "mode": "video",
                "processed_frames": 1,
                "class_counts": {},
                "key_frames": [],
            },
        ):
            resp = authenticated_client.post(
                "/api/segmentation/video",
                files={"file": ("test.mp4", video_bytes, "video/mp4")},
                data={"frame_sample_rate": 2, "max_frames": 3},
            )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["mode"] == "video"

    def test_chat_upload(self, authenticated_client: TestClient) -> None:
        image_bytes = io.BytesIO()
        Image.fromarray(np.zeros((64, 64, 3), dtype=np.uint8)).save(
            image_bytes, format="PNG"
        )
        image_bytes.seek(0)

        resp = authenticated_client.post(
            "/api/chat/upload",
            files={"file": ("test.png", image_bytes, "image/png")},
        )
        assert resp.status_code == 200, resp.text
        assert len(resp.json()["image_ref"]) == 32
        assert "image_path" not in resp.json()

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

    def test_tools_strip_annotated_image_from_llm_context(
        self, dummy_image: str
    ) -> None:
        """Base64 annotated images must be removed from the Agent observation."""
        from app.agent.detection_agent import segment_single_image

        with patch(
            "app.agent.detection_agent.detection_chat_service.segment_single",
            return_value={
                "mode": "single",
                "filename": "x.png",
                "annotated_image": "a" * 1000,
                "class_statistics": [{"pixel_count": 10}],
            },
        ):
            result = segment_single_image.invoke({"image_path": dummy_image})
            parsed = json.loads(result)
            assert parsed["mode"] == "single"
            assert "annotated_image" not in parsed
            assert parsed["class_statistics"][0]["pixel_count"] == 10

    def test_batch_tools_strip_nested_annotated_images(
        self, dummy_image: str
    ) -> None:
        """Nested annotated_image fields in batch results must also be stripped."""
        from app.agent.detection_agent import segment_batch_images

        with patch(
            "app.agent.detection_agent.detection_chat_service.segment_batch",
            return_value={
                "mode": "batch",
                "total_images": 1,
                "annotated_images": [
                    {
                        "filename": "x.png",
                        "annotated_image": "b" * 1000,
                        "class_statistics": [{"pixel_count": 5}],
                    }
                ],
            },
        ):
            result = segment_batch_images.invoke({"image_paths": [dummy_image]})
            parsed = json.loads(result)
            assert parsed["mode"] == "batch"
            assert "annotated_image" not in parsed["annotated_images"][0]
            assert parsed["annotated_images"][0]["class_statistics"][0]["pixel_count"] == 5


class TestDetectionAgentReliability:
    @pytest.mark.asyncio
    async def test_detection_executor_reuses_unified_factory(self) -> None:
        from app.agent.detection_agent import DetectionAgent

        fake_llm = object()
        fake_executor = object()
        agent = DetectionAgent()
        with patch(
            "app.agent.detection_agent.create_chat_llm", return_value=fake_llm
        ) as factory, patch(
            "app.agent.detection_agent.create_agent", return_value=fake_executor
        ) as create:
            assert agent._ensure_executor() is fake_executor

        factory.assert_called_once_with(temperature=0.1)
        create.assert_called_once()
        assert create.call_args.kwargs["model"] is fake_llm

    @pytest.mark.asyncio
    async def test_explicit_single_image_runs_locally_when_llm_unavailable(
        self, dummy_image: str
    ) -> None:
        from app.agent.detection_agent import DetectionAgent
        from app.agent.llm_streaming import LLMUnavailableError

        async def unavailable(*args, **kwargs):
            raise LLMUnavailableError("Missing credentials: sk-secret")
            yield  # pragma: no cover

        result = {
            "mode": "single",
            "filename": "dummy.png",
            "image_width": 64,
            "image_height": 64,
            "annotated_image": "aGVsbG8=",
            "class_statistics": [
                {"name": "building", "display_name": "建筑", "pixel_count": 2048, "ratio": 0.5}
            ],
        }
        with patch(
            "app.agent.detection_agent.detection_chat_service.segment_single",
            return_value=result,
        ) as infer, patch("app.agent.detection_agent.stream_llm_text", unavailable):
            events = [
                event
                async for event in DetectionAgent().chat_stream(
                    "请识别并分割", dummy_image, user_id=1
                )
            ]

        infer.assert_called_once_with(dummy_image, user_id=1, scene_id=None)
        assert [event["type"] for event in events] == [
            "tool_call",
            "tool_result",
            "text_chunk",
        ]
        assert events[0]["tool"] == "segment_single_image"
        assert dummy_image not in json.dumps(events[0], ensure_ascii=False)
        assert json.loads(events[1]["result"])["annotated_image"] == "aGVsbG8="
        assert "本地分割完成" in events[2]["content"]
        serialized = json.dumps(events, ensure_ascii=False)
        assert "Missing credentials" not in serialized
        assert "sk-secret" not in serialized

    @pytest.mark.asyncio
    async def test_summary_failure_preserves_result_and_sanitizes_llm_messages(
        self, dummy_image: str
    ) -> None:
        from app.agent.detection_agent import DetectionAgent

        captured = []

        async def broken_summary(messages, **kwargs):
            captured.extend(messages)
            raise RuntimeError("SDK stack with Missing credentials")
            yield  # pragma: no cover

        result = {
            "mode": "single",
            "filename": "dummy.png",
            "image_path": dummy_image,
            "image_width": 10,
            "image_height": 10,
            "annotated_image": "A" * 1000,
            "extra": "data:image/png;base64," + "B" * 500,
            "class_statistics": [
                {"name": "water", "display_name": "水体", "pixel_count": 100, "ratio": 1.0}
            ],
        }
        with patch(
            "app.agent.detection_agent.detection_chat_service.segment_single",
            return_value=result,
        ), patch("app.agent.detection_agent.stream_llm_text", broken_summary):
            events = [
                event
                async for event in DetectionAgent().chat_stream(
                    "分析 C:\\private\\secret.png 并分割", dummy_image
                )
            ]

        assert events[1]["type"] == "tool_result"
        assert events[-1]["type"] == "text_chunk"
        assert "水体" in events[-1]["content"]
        llm_payload = json.dumps(captured, ensure_ascii=False)
        assert dummy_image not in llm_payload
        assert "C:\\private\\secret.png" not in llm_payload
        assert "A" * 100 not in llm_payload
        assert "B" * 100 not in llm_payload
        assert "Missing credentials" not in json.dumps(events, ensure_ascii=False)
