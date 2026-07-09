"""Authentication endpoint tests."""

from fastapi.testclient import TestClient


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
