import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.exceptions import AppError
from app.knowledge.embeddings import EmbeddingProvider
from app.knowledge.service import KnowledgeService

DEFAULT_SEARCH_LIMIT = 5
MAX_SEARCH_LIMIT = 10
MAX_QUERY_LENGTH = 1000


class OrganizationNotConfiguredError(AppError):
    status_code = 500
    code = "organization_not_configured"

    def __init__(self) -> None:
        super().__init__(
            "Organization is not configured",
            details={"missing_env_vars": ["DEFAULT_ORGANIZATION_ID"]},
        )


class KnowledgeSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_QUERY_LENGTH),
        Field(description="What to look for in the organization's uploaded documents."),
    ]
    limit: int | None = Field(
        default=None,
        ge=1,
        le=MAX_SEARCH_LIMIT,
        description=f"Maximum number of passages to return (default {DEFAULT_SEARCH_LIMIT}).",
    )


class KnowledgeSearchTool:
    """Similarity search over uploaded documents. The model supplies a query, never SQL or a vector."""

    name = "search_knowledge"
    description = (
        "Search the organization's uploaded text and markdown documents. "
        "Returns each match's document_id, document name, passage, and a similarity score from 0 to 1. "
        "Use this for policies, guides, and other uploaded knowledge. "
        "Cite only document_id values from these results. "
        "Do not use it for live orders, refunds, or revenue (use analytics) or for arithmetic "
        "(use calculator)."
    )
    input_model = KnowledgeSearchInput

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        organization_id: uuid.UUID,
        embedder: EmbeddingProvider,
    ) -> None:
        self._session_factory = session_factory
        self._organization_id = organization_id
        self._embedder = embedder

    async def run(self, arguments: KnowledgeSearchInput) -> BaseModel:
        # Embed before opening a database session so the connection is not held during the API call.
        vector = await KnowledgeService.embed_query(self._embedder, arguments.query)
        async with self._read_only_session() as session:
            service = KnowledgeService(session, self._organization_id, self._embedder)
            return await service.search_by_vector(vector, arguments.limit or DEFAULT_SEARCH_LIMIT)

    @asynccontextmanager
    async def _read_only_session(self) -> AsyncIterator[AsyncSession]:
        async with self._session_factory() as session, session.begin():
            await session.execute(text("SET TRANSACTION READ ONLY"))
            await session.execute(text("SET LOCAL statement_timeout = '5s'"))
            yield session
