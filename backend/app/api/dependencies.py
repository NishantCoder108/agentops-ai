from typing import Annotated

from fastapi import Depends, FastAPI, Request

from app.agent.service import AgentService
from app.core.config import Settings
from app.llm.base import LLMProvider
from app.llm.factory import create_llm_provider
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


def get_tool_registry(request: Request) -> ToolRegistry:
    return request.app.state.tool_registry


def get_agent_service(
    provider: Annotated[LLMProvider, Depends(get_llm_provider)],
    tools: Annotated[ToolRegistry, Depends(get_tool_registry)],
) -> AgentService:
    return AgentService(provider, tools)


async def close_llm_provider(app: FastAPI) -> None:
    provider: LLMProvider | None = app.state.llm_provider
    if provider is not None:
        app.state.llm_provider = None
        await provider.aclose()
