import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agent.service import AgentService
from app.core.config import Settings
from app.db.errors import DatabaseNotConfiguredError
from app.knowledge.embeddings import EmbeddingProvider, create_embedding_provider
from app.llm.base import LLMProvider
from app.llm.factory import create_llm_provider
from app.tools import create_default_tool_registry
from app.tools.registry import ToolRegistry


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_llm_provider(
    request: Request, settings: Annotated[Settings, Depends(get_app_settings)]
) -> LLMProvider:
    # Created on first use so the app can start without LLM credentials; reused for the app's lifetime.
    provider: LLMProvider | None = request.app.state.llm_provider
    if provider is None:
        provider = create_llm_provider(settings)
        request.app.state.llm_provider = provider
    return provider


def get_current_organization_id(
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> uuid.UUID | None:
    # Placeholder until authentication: then this returns the authenticated user's organization.
    return settings.default_organization_id


def get_embedding_provider(
    request: Request, settings: Annotated[Settings, Depends(get_app_settings)]
) -> EmbeddingProvider:
    provider: EmbeddingProvider | None = request.app.state.embedding_provider
    if provider is None:
        provider = create_embedding_provider(settings)
        request.app.state.embedding_provider = provider
    return provider


def _optional_embedding_provider(request: Request, settings: Settings) -> EmbeddingProvider | None:
    api_key = settings.openrouter_api_key.get_secret_value() if settings.openrouter_api_key else ""
    if not settings.embedding_model or not api_key:
        return None
    return get_embedding_provider(request, settings)


def get_tool_registry(
    request: Request,
    settings: Annotated[Settings, Depends(get_app_settings)],
    organization_id: Annotated[uuid.UUID | None, Depends(get_current_organization_id)],
) -> ToolRegistry:
    return create_default_tool_registry(
        session_factory=request.app.state.db_session_factory,
        organization_id=organization_id,
        embedder=_optional_embedding_provider(request, settings),
    )


def get_agent_service(
    provider: Annotated[LLMProvider, Depends(get_llm_provider)],
    tools: Annotated[ToolRegistry, Depends(get_tool_registry)],
) -> AgentService:
    return AgentService(provider, tools)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """One session per request. Callers commit explicitly; uncommitted work is rolled back on close."""
    session_factory: async_sessionmaker[AsyncSession] | None = request.app.state.db_session_factory
    if session_factory is None:
        raise DatabaseNotConfiguredError()
    async with session_factory() as session:
        yield session


async def close_embedding_provider(app: FastAPI) -> None:
    provider: EmbeddingProvider | None = app.state.embedding_provider
    if provider is not None:
        app.state.embedding_provider = None
        await provider.aclose()


async def close_llm_provider(app: FastAPI) -> None:
    provider: LLMProvider | None = app.state.llm_provider
    if provider is not None:
        app.state.llm_provider = None
        await provider.aclose()


async def close_database(app: FastAPI) -> None:
    engine: AsyncEngine | None = app.state.db_engine
    if engine is not None:
        await engine.dispose()
