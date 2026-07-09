"""Health endpoint tests."""

from fastapi.testclient import TestClient

from main import app


def test_health_check_basic() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "app_name" in data
    assert "version" in data


def test_health_detail_returns_degraded_when_dependency_fails(monkeypatch) -> None:
    from app.api import health

    monkeypatch.setattr(health, "_check_postgresql", lambda: {"status": "healthy", "message": "ok"})
    monkeypatch.setattr(health, "_check_redis", lambda: {"status": "unhealthy", "message": "failed"})
    monkeypatch.setattr(health, "_check_minio", lambda: {"status": "healthy", "message": "ok"})

    with TestClient(app) as client:
        response = client.get("/api/health/detail")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["dependencies"]["redis"]["status"] == "unhealthy"
