import pytest

from app.agent import DEFAULT_SYSTEM_PROMPT, AgentService
from app.core.exceptions import AppError
from app.llm import ChatMessage, LLMProvider, LLMProviderError
from tests.fakes import FakeLLMProvider

pytestmark = pytest.mark.anyio


@pytest.fixture
def provider() -> FakeLLMProvider:
    return FakeLLMProvider(reply="Hi there!")


@pytest.fixture
def agent(provider: FakeLLMProvider) -> AgentService:
    typed_provider: LLMProvider = provider
    return AgentService(typed_provider)


async def test_run_returns_model_answer(agent: AgentService) -> None:
    assert await agent.run("Hello") == "Hi there!"


async def test_run_sends_system_prompt_and_user_message(
    agent: AgentService, provider: FakeLLMProvider
) -> None:
    await agent.run("Hello")

    assert len(provider.calls) == 1
    assert provider.calls[0]["messages"] == [
        ChatMessage(role="system", content=DEFAULT_SYSTEM_PROMPT),
        ChatMessage(role="user", content="Hello"),
    ]


async def test_run_uses_custom_system_prompt(provider: FakeLLMProvider) -> None:
    agent = AgentService(provider, system_prompt="Reply in French.")

    await agent.run("Hello")

    assert provider.calls[0]["messages"][0] == ChatMessage(role="system", content="Reply in French.")


async def test_run_rejects_empty_message(agent: AgentService, provider: FakeLLMProvider) -> None:
    with pytest.raises(AppError) as exc_info:
        await agent.run("   ")

    assert exc_info.value.code == "invalid_message"
    assert provider.calls == []


async def test_run_propagates_provider_errors() -> None:
    agent = AgentService(FakeLLMProvider(error=LLMProviderError("LLM provider returned an error")))

    with pytest.raises(LLMProviderError):
        await agent.run("Hello")
