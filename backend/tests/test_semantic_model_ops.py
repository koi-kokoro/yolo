"""Tests for semantic model lifecycle operations (evaluate/export/versions)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.entity.db_models import ModelVersion


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


def test_evaluate_returns_cached_metrics(
    authenticated_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.semantic_model_ops._load_cached_metrics",
        lambda *_args: {"overall": {"miou": 0.5}},
    )
    resp = authenticated_client.post("/api/semantic-models/evaluate", json={"device": "cpu", "force": False})
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "cached"
    assert "overall" in data["report"]
    assert "miou" in data["report"]["overall"]


def test_export_creates_model_version(authenticated_client: TestClient, db_session: Session) -> None:
    resp = authenticated_client.post(
        "/api/semantic-models/export",
        json={"version": "v1.0.0-test", "description": "test", "set_default": True, "upload_minio": False},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["version"] == "v1.0.0-test"
    assert data["is_default"] is True

    model = db_session.query(ModelVersion).filter(ModelVersion.id == data["model_version_id"]).first()
    assert model is not None
    assert model.task_kind == "semantic_segmentation"


def test_list_versions(authenticated_client: TestClient) -> None:
    resp = authenticated_client.get("/api/semantic-models/versions")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    for item in data["items"]:
        assert {"model_path", "runtime", "artifact_sha256", "task_kind"} <= item.keys()
