
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.main import app
from app.models.role import Role
from app.models.user import User
from app.routers.auth import get_db as auth_get_db


# Separate in-memory SQLite database for authentication tests.
test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    bind=test_engine,
    autoflush=False,
    autocommit=False,
)


@pytest.fixture
def auth_client():
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()

    db.add(Role(name="Customer", description="Test customer"))
    db.commit()

    def override_get_db():
        yield db

    app.dependency_overrides[auth_get_db] = override_get_db

    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(auth_get_db, None)
        db.close()
        Base.metadata.drop_all(bind=test_engine)


def register_test_user(
    client,
    email="test@example.com",
    password="TestPassword123",
):
    response = client.post(
        "/auth/register",
        json={
            "full_name": "Test User",
            "email": email,
            "password": password,
        },
    )
    return response


def login_test_user(
    client,
    email="test@example.com",
    password="TestPassword123",
):
    return client.post(
        "/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )


def test_register_user(auth_client):
    response = register_test_user(auth_client)

    assert response.status_code == 201
    assert response.json()["email"] == "test@example.com"


def test_register_duplicate_email(auth_client):
    first_response = register_test_user(auth_client)
    second_response = register_test_user(auth_client)

    assert first_response.status_code == 201
    assert second_response.status_code == 409


def test_login_invalid_credentials(auth_client):
    response = login_test_user(
        auth_client,
        email="unknown@example.com",
        password="WrongPassword123",
    )

    assert response.status_code == 401


def test_register_password_too_short(auth_client):
    response = auth_client.post(
        "/auth/register",
        json={
            "full_name": "Test User",
            "email": "short@example.com",
            "password": "short",
        },
    )

    assert response.status_code == 422


def test_login_success(auth_client):
    register_response = register_test_user(auth_client)
    assert register_response.status_code == 201

    response = login_test_user(auth_client)

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert response.json()["refresh_token"]


def test_get_current_user(auth_client):
    register_test_user(auth_client)

    login_response = login_test_user(auth_client)
    access_token = login_response.json()["access_token"]

    response = auth_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    assert response.json()["email"] == "test@example.com"


def test_get_current_user_without_token(auth_client):
    response = auth_client.get("/auth/me")

    assert response.status_code in (401, 403)


def test_login_inactive_user(auth_client):
    register_response = register_test_user(
        auth_client,
        email="inactive@example.com",
    )
    assert register_response.status_code == 201

    db = TestingSessionLocal()
    try:
        user = (
            db.query(User)
            .filter(User.email == "inactive@example.com")
            .first()
        )
        assert user is not None

        user.is_active = False
        db.commit()
    finally:
        db.close()

    response = login_test_user(
        auth_client,
        email="inactive@example.com",
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "User account is inactive"


def test_refresh_token_success(auth_client):
    register_test_user(auth_client)

    login_response = login_test_user(auth_client)
    assert login_response.status_code == 200

    refresh_token = login_response.json()["refresh_token"]

    response = auth_client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == 200
    assert response.json()["access_token"]


def test_logout_revokes_refresh_token(auth_client):
    register_test_user(auth_client)

    login_response = login_test_user(auth_client)
    assert login_response.status_code == 200

    refresh_token = login_response.json()["refresh_token"]

    logout_response = auth_client.post(
        "/auth/logout",
        json={"refresh_token": refresh_token},
    )

    assert logout_response.status_code == 200
    assert logout_response.json()["message"] == "Logged out successfully"

    refresh_response = auth_client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert refresh_response.status_code == 401


def test_change_password_success(auth_client):
    register_test_user(auth_client)

    login_response = login_test_user(auth_client)
    assert login_response.status_code == 200

    access_token = login_response.json()["access_token"]

    response = auth_client.post(
        "/auth/change-password",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "current_password": "TestPassword123",
            "new_password": "NewPassword123",
        },
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Password changed successfully"

    new_login_response = login_test_user(
        auth_client,
        password="NewPassword123",
    )

    assert new_login_response.status_code == 200


def test_change_password_wrong_current_password(auth_client):
    register_test_user(auth_client)

    login_response = login_test_user(auth_client)
    assert login_response.status_code == 200

    access_token = login_response.json()["access_token"]

    response = auth_client.post(
        "/auth/change-password",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "current_password": "WrongCurrentPassword123",
            "new_password": "NewPassword123",
        },
    )

    assert response.status_code == 400


def test_refresh_token_rejects_invalid_token(auth_client):
    response = auth_client.post(
        "/auth/refresh",
        json={"refresh_token": "invalid-refresh-token"},
    )

    assert response.status_code == 401


def test_logout_rejects_invalid_token(auth_client):
    response = auth_client.post(
        "/auth/logout",
        json={"refresh_token": "invalid-refresh-token"},
    )

    assert response.status_code == 401


def test_current_user_rejects_invalid_access_token(auth_client):
    response = auth_client.get(
        "/auth/me",
        headers={"Authorization": "Bearer invalid-access-token"},
    )

    assert response.status_code == 401
