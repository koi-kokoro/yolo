"""Authentication endpoint tests."""

from fastapi.testclient import TestClient

from app.config.settings import settings
from app.entity.db_models import Role, User


def test_register_login_and_me(client: TestClient) -> None:
    register_response = client.post(
        "/api/auth/register",
        json={
            "username": "tester",
            "email": "tester@example.com",
            "password": "password123",
        },
    )

    assert register_response.status_code == 201
    registered_user = register_response.json()
    assert registered_user["username"] == "tester"
    assert registered_user["email"] == "tester@example.com"
    assert "hashed_password" not in registered_user

    login_response = client.post(
        "/api/auth/login",
        json={"username": "tester", "password": "password123"},
    )

    assert login_response.status_code == 200
    token_data = login_response.json()
    assert token_data["token_type"] == "bearer"
    assert token_data["access_token"]
    assert token_data["user"]["username"] == "tester"

    me_response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token_data['access_token']}"},
    )

    assert me_response.status_code == 200
    current_user = me_response.json()
    assert current_user["username"] == "tester"
    assert current_user["email"] == "tester@example.com"


def test_register_without_admin_code_creates_regular_user(client: TestClient, db_session) -> None:
    response = client.post(
        "/api/auth/register",
        json={
            "username": "regular-user",
            "email": "regular@example.com",
            "password": "password123",
        },
    )

    assert response.status_code == 201
    user = db_session.query(User).filter(User.username == "regular-user").one()
    assert user.is_superuser is False


def test_register_with_correct_admin_code_creates_superuser(client: TestClient, db_session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "ADMIN_REGISTRATION_CODE", "test-admin-code")
    db_session.add(
        Role(name="admin", display_name="管理员", is_system=True)
    )
    db_session.commit()

    response = client.post(
        "/api/auth/register",
        json={
            "username": "admin-user",
            "email": "admin@example.com",
            "password": "password123",
            "admin_code": "test-admin-code",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["is_superuser"] is True
    assert body["roles"] == ["admin"]
    assert "admin_code" not in body


def test_register_with_wrong_admin_code_does_not_create_user(client: TestClient, db_session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "ADMIN_REGISTRATION_CODE", "test-admin-code")

    response = client.post(
        "/api/auth/register",
        json={
            "username": "rejected-admin",
            "email": "rejected@example.com",
            "password": "password123",
            "admin_code": "wrong-code",
        },
    )

    assert response.status_code == 400
    assert response.json()["message"] == "管理员代码错误"
    assert db_session.query(User).filter(User.username == "rejected-admin").count() == 0
    assert db_session.query(User).filter(User.email == "rejected@example.com").count() == 0


def test_login_with_wrong_password_returns_401(client: TestClient) -> None:
    client.post(
        "/api/auth/register",
        json={
            "username": "wrongpass",
            "email": "wrongpass@example.com",
            "password": "password123",
        },
    )

    response = client.post(
        "/api/auth/login",
        json={"username": "wrongpass", "password": "bad-password"},
    )

    assert response.status_code == 401
    data = response.json()
    assert data["success"] is False
    assert data["message"] == "密码错误"
