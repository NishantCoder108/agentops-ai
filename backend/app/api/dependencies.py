import uuid
from collections.abc import AsyncIterator, Callable
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agent.service import AgentService
from app.auth.errors import ForbiddenError, UnauthorizedError
from app.auth.permissions import Permission, permissions_for
from app.auth.tokens import decode_access_token
from app.core.config import Settings
from app.db.errors import DatabaseNotConfiguredError
from app.rate_limit import RateLimiter, RateLimitedError
from app.knowledge.embeddings import EmbeddingProvider, create_embedding_provider
from app.llm.base import LLMProvider
from app.llm.factory import create_llm_provider
from app.models import User
from app.tools import create_default_tool_registry
from app.tools.registry import ToolRegistry

_bearer = HTTPBearer(auto_error=False)


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


async def get_current_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_app_settings)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """Load the user for a bearer token. The token is checked before a database connection is opened."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthorizedError()
    user_id = decode_access_token(settings, credentials.credentials)
    session_factory: async_sessionmaker[AsyncSession] | None = request.app.state.db_session_factory
    if session_factory is None:
        raise DatabaseNotConfiguredError()
    async with session_factory() as session:
        user = await session.get(User, user_id)
        if user is None:
            raise UnauthorizedError()
        session.expunge(user)
        return user


def require_permission(permission: str) -> Callable[..., object]:
    async def checker(user: Annotated[User, Depends(get_current_user)]) -> User:
        if permission not in permissions_for(user.role):
            raise ForbiddenError()
        return user

    return checker


_chat_user = require_permission(Permission.CHAT)


async def enforce_chat_rate_limit(
    request: Request,
    user: Annotated[User, Depends(_chat_user)],
) -> User:
    """Count one chat request. A user who cannot chat is rejected before the counter moves."""
    settings: Settings = request.app.state.settings
    limiter: RateLimiter = request.app.state.rate_limiter
    decision = await limiter.consume(
        "chat",
        str(user.id),
        limit=settings.chat_rate_limit_requests,
        window_seconds=settings.chat_rate_limit_window_seconds,
    )
    if not decision.allowed:
        raise RateLimitedError(decision.retry_after_seconds)
    return user


def get_current_organization_id(user: Annotated[User, Depends(get_current_user)]) -> uuid.UUID:
    return user.organization_id


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
    user: Annotated[User, Depends(get_current_user)],
) -> ToolRegistry:
    embedder = None
    if Permission.SEARCH_KNOWLEDGE in permissions_for(user.role):
        embedder = _optional_embedding_provider(request, settings)
    return create_default_tool_registry(
        session_factory=request.app.state.db_session_factory,
        organization_id=user.organization_id,
        embedder=embedder,
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
