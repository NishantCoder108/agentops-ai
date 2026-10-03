"""Fixtures for tests that need a real PostgreSQL database.

The schema is built by running the Alembic migrations (so the migrations themselves are tested),
and every table is truncated after each test.
"""

import asyncio
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.base import Base
from app.db.session import create_session_factory, prepare_engine

BACKEND_DIR = Path(__file__).resolve().parents[2]


class DatabaseTestSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    # Matches the docker-compose.yml defaults.
    test_database_url: str = "postgresql+asyncpg://agentops:agentops@localhost:5432/agentops_test"


def alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["database_url"] = database_url
    config.attributes["configure_logging"] = False
    return config


async def _connection_error(database_url: str) -> str | None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with asyncio.timeout(3), engine.connect():
            return None
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def database_url() -> str:
    url = DatabaseTestSettings().test_database_url
    database = make_url(url).database or ""
    if not database.endswith("_test"):
        pytest.fail(
            f"TEST_DATABASE_URL must point to a dedicated '*_test' database (got {database!r}); "
            "the tests delete all of its data."
        )
    error = asyncio.run(_connection_error(url))
    if error is not None:
        pytest.skip(
            f"PostgreSQL test database {database!r} is not reachable ({error}). "
            "Start it with `docker compose up -d postgres` from the repository root."
        )
    return url


@pytest.fixture(scope="session")
def migrated_database(database_url: str) -> str:
    config = alembic_config(database_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    return database_url


async def _truncate_all_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
        await connection.execute(text(f"TRUNCATE {tables} CASCADE"))


async def _truncate_database(database_url: str) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        await _truncate_all_tables(engine)
    finally:
        await engine.dispose()


@pytest.fixture
def clean_database(migrated_database: str) -> Iterator[str]:
    """For sync tests (e.g. through TestClient): yields the URL and empties all tables afterwards."""
    yield migrated_database
    asyncio.run(_truncate_database(migrated_database))


@pytest.fixture
async def db_engine(migrated_database: str) -> AsyncIterator[AsyncEngine]:
    engine = prepare_engine(create_async_engine(migrated_database, poolclass=NullPool))
    yield engine
    await _truncate_all_tables(engine)
    await engine.dispose()


@pytest.fixture
def session_factory(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(db_engine)


@pytest.fixture
async def db_session(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
