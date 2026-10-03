import asyncio

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, inspect
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.base import Base
from tests.db.conftest import alembic_config

EXPECTED_TABLES = {
    "organizations",
    "users",
    "customers",
    "orders",
    "refunds",
    "conversations",
    "messages",
    "agent_runs",
    "tool_calls",
    "documents",
    "document_chunks",
}


async def _table_names(database_url: str) -> set[str]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            names = await connection.run_sync(lambda sync: set(inspect(sync).get_table_names()))
    finally:
        await engine.dispose()
    return names - {"alembic_version"}


def test_single_migration_head() -> None:
    script = ScriptDirectory.from_config(alembic_config("unused"))

    assert len(script.get_heads()) == 1


@pytest.mark.asyncio
async def test_migrations_match_models(db_engine: AsyncEngine) -> None:
    def diff(connection: Connection) -> list:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        return compare_metadata(context, Base.metadata)

    async with db_engine.connect() as connection:
        assert await connection.run_sync(diff) == []


def test_downgrade_and_upgrade_round_trip(migrated_database: str) -> None:
    config = alembic_config(migrated_database)
    assert asyncio.run(_table_names(migrated_database)) == EXPECTED_TABLES

    try:
        command.downgrade(config, "base")
        assert asyncio.run(_table_names(migrated_database)) == set()
    finally:
        command.upgrade(config, "head")

    assert asyncio.run(_table_names(migrated_database)) == EXPECTED_TABLES
