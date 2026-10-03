from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.main import create_app
from app.models import Organization
from tests.conftest import make_settings

DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def make_app(database_url: str) -> FastAPI:
    app = create_app(make_settings(database_url=database_url))

    @app.post("/test/orgs")
    async def create_org(session: DbSession, commit: bool = True) -> dict:
        organization = Organization(name="Via API")
        session.add(organization)
        await session.flush()
        if commit:
            await session.commit()
        return {"id": str(organization.id)}

    @app.get("/test/orgs/count")
    async def count_orgs(session: DbSession) -> int:
        return (await session.execute(select(func.count()).select_from(Organization))).scalar_one()

    return app


def test_db_session_dependency_commits_changes(clean_database: str) -> None:
    with TestClient(make_app(clean_database)) as client:
        assert client.post("/test/orgs").status_code == 200
        assert client.get("/test/orgs/count").json() == 1


def test_uncommitted_changes_are_rolled_back_after_request(clean_database: str) -> None:
    with TestClient(make_app(clean_database)) as client:
        assert client.post("/test/orgs", params={"commit": False}).status_code == 200
        assert client.get("/test/orgs/count").json() == 0
