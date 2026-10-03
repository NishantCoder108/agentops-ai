import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.dependencies import get_llm_provider
from app.db.session import prepare_engine
from app.main import create_app
from app.models import User
from tests.auth_helpers import JWT_SECRET, PASSWORD, bearer, login, register
from tests.conftest import make_settings
from tests.fakes import FakeLLMProvider, answer_response


def _app(database_url: str):
    return create_app(make_settings(database_url=database_url, jwt_secret=JWT_SECRET))


def test_registration_creates_an_admin_and_a_token(clean_database: str) -> None:
    with TestClient(_app(clean_database)) as client:
        created = register(client, email="Ada@Example.com")

        assert created["token_type"] == "bearer"
        assert created["access_token"]
        assert created["user"]["role"] == "admin"
        assert created["user"]["email"] == "ada@example.com"
        assert PASSWORD not in created["access_token"]

        me = client.get("/api/v1/auth/me", headers=bearer(created["access_token"]))
        assert me.status_code == 200
        assert me.json()["id"] == created["user"]["id"]
        assert "password" not in me.text

        duplicate = client.post(
            "/api/v1/auth/register",
            json={
                "email": "ada@example.com",
                "name": "Ada",
                "password": PASSWORD,
                "organization_name": "Other",
            },
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["code"] == "email_taken"

    stored = asyncio.run(_password_hash(clean_database, "ada@example.com"))
    assert stored != PASSWORD
    assert PASSWORD not in stored
    assert stored.startswith("$argon2")


def test_login_accepts_the_right_password(clean_database: str) -> None:
    with TestClient(_app(clean_database)) as client:
        register(client)
        token = login(client, "ada@example.com")

        me = client.get("/api/v1/auth/me", headers=bearer(token))
        assert me.status_code == 200
        assert me.json()["email"] == "ada@example.com"


def test_login_rejects_an_invalid_password(clean_database: str) -> None:
    with TestClient(_app(clean_database)) as client:
        register(client)
        wrong = client.post(
            "/api/v1/auth/login",
            json={"email": "ada@example.com", "password": "wrong-password"},
        )
        unknown = client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "wrong-password"},
        )

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.json()["error"]["code"] == "invalid_credentials"


@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("get", "/api/v1/auth/me", None),
        ("post", "/api/v1/chat", {"message": "Hello"}),
        ("get", "/api/v1/conversations", None),
        ("get", "/api/v1/agent-runs", None),
        ("get", "/api/v1/users", None),
        ("post", "/api/v1/users", {"email": "a@b.co", "name": "A", "password": PASSWORD}),
    ],
)
def test_protected_routes_reject_missing_tokens(
    clean_database: str, method: str, path: str, json_body: dict | None
) -> None:
    with TestClient(_app(clean_database)) as client:
        response = client.request(method, path, json=json_body)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_health_stays_public(clean_database: str) -> None:
    with TestClient(_app(clean_database)) as client:
        assert client.get("/api/v1/health").status_code == 200
        rejected = client.post(
            "/api/v1/documents",
            files={"file": ("notes.md", b"hello", "text/markdown")},
        )
        assert rejected.status_code == 401
        assert rejected.json()["error"]["code"] == "unauthorized"


def test_roles_authorize_admin_and_user_routes(clean_database: str) -> None:
    app = _app(clean_database)
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider(reply="Four.")
    with TestClient(app) as client:
        admin = register(client, email="admin@example.com")
        admin_headers = bearer(admin["access_token"])
        created = client.post(
            "/api/v1/users",
            headers=admin_headers,
            json={"email": "member@example.com", "name": "Member", "password": PASSWORD, "role": "user"},
        )
        assert created.status_code == 201
        assert created.json()["role"] == "user"
        assert "password" not in created.text
        user_headers = bearer(login(client, "member@example.com"))

        assert client.post("/api/v1/chat", headers=admin_headers, json={"message": "Hi"}).status_code == 403
        assert client.get("/api/v1/conversations", headers=admin_headers).status_code == 403
        assert client.get("/api/v1/users", headers=user_headers).status_code == 403
        assert client.get("/api/v1/agent-runs", headers=user_headers).status_code == 403
        assert (
            client.post(
                "/api/v1/documents",
                headers=user_headers,
                files={"file": ("notes.md", b"hello", "text/markdown")},
            ).status_code
            == 403
        )

        chat = client.post("/api/v1/chat", headers=user_headers, json={"message": "Hi"})
        assert chat.status_code == 200
        conversation_id = chat.json()["conversation_id"]
        listed = client.get("/api/v1/conversations", headers=user_headers)
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [conversation_id]

        runs = client.get("/api/v1/agent-runs", headers=admin_headers)
        assert runs.status_code == 200
        assert runs.json()[0]["conversation_id"] == conversation_id
        assert runs.json()[0]["final_answer"] == "Four."
        assert "password" not in runs.text

        other = register(client, email="other@example.com", organization_name="Other")
        other_runs = client.get("/api/v1/agent-runs", headers=bearer(other["access_token"]))
        assert other_runs.status_code == 200
        assert other_runs.json() == []


def test_a_user_cannot_read_someone_elses_conversation(clean_database: str) -> None:
    app = _app(clean_database)
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider(
        responses=[answer_response("Hello")]
    )
    with TestClient(app) as client:
        admin = register(client, email="admin@example.com")
        admin_headers = bearer(admin["access_token"])
        for email in ("one@example.com", "two@example.com"):
            assert (
                client.post(
                    "/api/v1/users",
                    headers=admin_headers,
                    json={"email": email, "name": email, "password": PASSWORD, "role": "user"},
                ).status_code
                == 201
            )
        one = bearer(login(client, "one@example.com"))
        two = bearer(login(client, "two@example.com"))
        chat = client.post("/api/v1/chat", headers=one, json={"message": "Hi"})
        conversation_id = chat.json()["conversation_id"]

        assert client.get("/api/v1/conversations", headers=two).json() == []
        hidden = client.get(f"/api/v1/conversations/{conversation_id}", headers=two)
        assert hidden.status_code == 404
        assert hidden.json()["error"]["code"] == "not_found"
        assert client.get(f"/api/v1/conversations/{conversation_id}", headers=one).status_code == 200


async def _password_hash(database_url: str, email: str) -> str:
    engine = prepare_engine(create_async_engine(database_url, poolclass=NullPool))
    try:
        async with async_sessionmaker(engine)() as session:
            stored = await session.scalar(select(User.password_hash).where(User.email == email))
    finally:
        await engine.dispose()
    assert stored is not None
    return stored
