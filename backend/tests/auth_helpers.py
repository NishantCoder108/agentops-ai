import uuid
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.models import UserRole

JWT_SECRET = "unit-test-jwt-secret-0123456789ab"
PASSWORD = "correct-horse-battery"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def install_user(
    app: FastAPI,
    *,
    role: UserRole = UserRole.USER,
    organization_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> SimpleNamespace:
    """Skip token verification. Use a real token when the user must exist in the database."""
    user = SimpleNamespace(
        id=user_id or uuid.uuid4(),
        organization_id=organization_id or uuid.uuid4(),
        role=role,
        email="ada@example.com",
        name="Ada",
        password_hash="not-used",
    )
    app.dependency_overrides[get_current_user] = lambda: user
    return user


def register(client: TestClient, **overrides: str) -> dict:
    body = {
        "email": "ada@example.com",
        "name": "Ada",
        "password": PASSWORD,
        "organization_name": "Acme",
    }
    body.update(overrides)
    response = client.post("/api/v1/auth/register", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def login(client: TestClient, email: str, password: str = PASSWORD) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]
