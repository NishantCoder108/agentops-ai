import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Environment
from app.main import create_app
from tests.conftest import make_settings


def test_defaults_are_development() -> None:
    settings = make_settings()

    assert settings.environment == Environment.DEVELOPMENT
    assert settings.debug is False
    assert settings.api_v1_prefix == "/api/v1"
    assert settings.docs_enabled is True


def test_cors_origins_parsed_from_comma_separated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://a.example, http://b.example")

    settings = make_settings()

    assert settings.cors_origins == ["http://a.example", "http://b.example"]


def test_production_rejects_debug() -> None:
    with pytest.raises(ValidationError, match="DEBUG must be false"):
        make_settings(environment="production", debug=True)


def test_production_rejects_wildcard_cors() -> None:
    with pytest.raises(ValidationError, match="must not contain"):
        make_settings(environment="production", cors_origins=["*"])


def test_production_requires_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        make_settings(environment="production")


def test_production_requires_redis_url() -> None:
    with pytest.raises(ValidationError, match="REDIS_URL"):
        make_settings(environment="production", jwt_secret="x" * 32)


def test_production_disables_docs() -> None:
    client = TestClient(
        create_app(
            make_settings(
                environment="production",
                jwt_secret="x" * 32,
                redis_url="redis://localhost:6379/0",
            )
        )
    )

    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/api/v1/health").status_code == 200


def test_cors_allows_configured_origin(client: TestClient) -> None:
    response = client.options(
        "/api/v1/health",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_rejects_unknown_origin(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"Origin": "http://evil.example"})

    assert "access-control-allow-origin" not in response.headers
