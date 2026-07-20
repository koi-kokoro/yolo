"""DIOR facility detection service and routing tests without model dependencies."""

from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image

from app.entity.db_models import DetectionResult, DetectionScene, DetectionTask, ModelVersion, User
from app.orchestration.supervisor import Supervisor
from app.api.chat import _merge_detection_tool_result, _requests_session_image
from app.services.facility_detection_service import FacilityDetectionService
from app.utils.image_validation import ValidatedImage


class FakeEngine:
    metadata = {
        "model": "dior-yolo11n",
        "version": "test-v1",
        "task": "detection",
        "input_size": 640,
        "classes": ["airplane"] * 20,
    }
    metrics = {"map50": 0.87, "map50_95": 0.65, "precision": 0.9, "recall": 0.81}
    model_sha256 = "a" * 64


class FakeRuntime:
    ready = True
    error = None
    engine = FakeEngine()

    def model_info(self):
        return {
            "ready": True,
            "model": "dior-yolo11n",
            "version": "test-v1",
            "classes": [{"id": 0, "name": "airplane"}],
        }

    def predict(self, image, conf, iou, image_size):
        assert image.size == (32, 24)
        assert conf == 0.25
        assert iou == 0.45
        assert image_size == 640
        return {
            "detections": [
                {
                    "class_id": 0,
                    "class_name": "airplane",
                    "confidence": 0.91,
                    "bbox": {"x1": 1.0, "y1": 2.0, "x2": 20.0, "y2": 18.0},
                }
            ],
            "annotated_jpeg": b"jpeg-result",
            "inference_time_ms": 12.5,
        }


class FakeStorage:
    def __init__(self):
        self.objects = {}

    def upload_file(self, key, path, content_type=None):
        self.objects[key] = Path(path).read_bytes()
        return key

    def upload_bytes(self, key, data, content_type="image/jpeg"):
        self.objects[key] = data
        return key

    def get_presigned_url(self, key):
        return f"https://objects.test/{key}"


def _validated_image(tmp_path: Path) -> ValidatedImage:
    path = tmp_path / "sample.png"
    Image.new("RGB", (32, 24), "white").save(path)
    image = Image.open(path).convert("RGB")
    data = path.read_bytes()
    return ValidatedImage(
        temp_path=path,
        image=image,
        width=32,
        height=24,
        sha256=hashlib.sha256(data).hexdigest(),
        content_type="image/png",
        canonical_ext=".png",
        original_filename="sample.png",
    )


def test_service_persists_dior_task_and_boxes(db_session, tmp_path):
    user = User(username="dior-user", email="dior@test.local", hashed_password="x")
    db_session.add(user)
    db_session.commit()
    service = FacilityDetectionService()
    service.runtime = FakeRuntime()
    service._storage = FakeStorage()
    validated = _validated_image(tmp_path)
    try:
        result = service.detect(db_session, user.id, [validated], 0.25, 0.45, 640)
    finally:
        validated.image.close()

    assert result["total_objects"] == 1
    assert result["class_statistics"] == [
        {"class_name": "airplane", "class_name_cn": "飞机", "count": 1}
    ]
    task = db_session.query(DetectionTask).one()
    assert task.status == "completed"
    assert task.total_objects == 1
    detection = db_session.query(DetectionResult).one()
    assert detection.bbox == {"x1": 1.0, "y1": 2.0, "x2": 20.0, "y2": 18.0}
    assert db_session.query(DetectionScene).one().name == "dior_facility_detection"
    assert db_session.query(ModelVersion).one().task_kind == "detection"


def test_supervisor_only_routes_explicit_facility_intent_to_dior():
    supervisor = Supervisor()
    assert supervisor.route("分析这张图片", "trusted.png") == "detection"
    assert supervisor.route("检测图片里的船舶和储油罐", "trusted.png") == "facility_detection"
    assert supervisor.route("运行 DIOR 设施检测") == "facility_detection"


def test_generic_image_inspection_runs_both_complementary_models():
    plan = Supervisor().plan("帮我看看这个图里有什么东西", "trusted.png")
    assert plan.primary_route == "combined_detection"
    assert [(step.id, step.agent) for step in plan.steps] == [
        ("land_cover", "detection"),
        ("facilities", "facility_detection"),
    ]


def test_explicit_image_intent_keeps_single_model_route():
    supervisor = Supervisor()
    semantic = supervisor.plan("分析这张图的土地覆盖和水体占比", "trusted.png")
    facility = supervisor.plan("检测这张图里的船舶和储油罐", "trusted.png")
    assert [step.agent for step in semantic.steps] == ["detection"]
    assert [step.agent for step in facility.steps] == ["facility_detection"]


def test_follow_up_wording_reuses_latest_session_image():
    assert _requests_session_image("检测一下图里都有什么东西") is True
    assert _requests_session_image("检测一下图例都有什么东西") is True
    assert _requests_session_image("看看刚才那张图有哪些目标") is True


def test_chat_persistence_keeps_both_detection_payloads():
    semantic = {"mode": "single", "class_statistics": [{"name": "water"}]}
    facility = {"kind": "facility_detection", "total_objects": 2, "images": []}
    merged = _merge_detection_tool_result(None, "semantic", semantic)
    merged = _merge_detection_tool_result(merged, "facility_detection", facility)
    import json

    payload = json.loads(merged)
    assert payload["kind"] == "combined_detection"
    assert payload["semantic"] == semantic
    assert payload["facility_detection"] == facility
