from typing import Annotated

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.main import create_app
from tests.conftest import make_settings

URL = "postgresql+asyncpg://agentops:s3cret@localhost:5432/agentops"


def test_database_url_is_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert make_settings().database_url is None


def test_empty_database_url_means_unset() -> None:
    assert make_settings(database_url="  ").database_url is None


def test_empty_organization_id_means_unset() -> None:
    assert make_settings(default_organization_id="  ").default_organization_id is None


def test_organization_id_is_read_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEFAULT_ORGANIZATION_ID", "7f1c7b7e-3c2e-4a59-9d39-2b0f5c3d8a10")

    assert str(make_settings().default_organization_id) == "7f1c7b7e-3c2e-4a59-9d39-2b0f5c3d8a10"


def test_database_url_is_read_from_env_and_kept_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", URL)

    settings = make_settings()

    assert settings.database_url is not None
    assert settings.database_url.get_secret_value() == URL
    assert "s3cret" not in repr(settings)


@pytest.mark.parametrize(
    "url",
    ["postgresql://u:p@localhost/db", "postgresql+psycopg://u:p@localhost/db", "sqlite+aiosqlite:///x.db"],
)
def test_database_url_must_use_asyncpg(url: str) -> None:
    with pytest.raises(ValidationError, match="postgresql\\+asyncpg://"):
        make_settings(database_url=url)


def test_app_without_database_has_no_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    app = create_app(make_settings())

    assert app.state.db_engine is None
    assert app.state.db_session_factory is None


def test_app_with_database_url_creates_engine_without_connecting() -> None:
    # Port 1 is never a PostgreSQL server: creating the engine must not open a connection.
    app = create_app(make_settings(database_url="postgresql+asyncpg://u:p@127.0.0.1:1/none"))

    assert app.state.db_engine is not None
    assert app.state.db_session_factory is not None


def test_db_session_without_database_returns_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    app = create_app(make_settings())

    @app.get("/needs-db")
    async def needs_db(session: Annotated[AsyncSession, Depends(get_db_session)]) -> None:
        pass

    response = TestClient(app, raise_server_exceptions=False).get("/needs-db")

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "database_not_configured",
            "message": "Database is not configured",
            "details": {"missing_env_vars": ["DATABASE_URL"]},
        }
    }
