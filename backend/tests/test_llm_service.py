import pytest

from app.core.exceptions import AppError
from app.llm import ChatMessage, LLMProvider
from app.services.llm_service import LLMService
from tests.fakes import FakeLLMProvider

pytestmark = pytest.mark.anyio


@pytest.fixture
def provider() -> FakeLLMProvider:
    return FakeLLMProvider()


@pytest.fixture
def service(provider: FakeLLMProvider) -> LLMService:
    typed_provider: LLMProvider = provider
    return LLMService(typed_provider)


async def test_generate_returns_provider_response(service: LLMService) -> None:
    response = await service.generate("Hi")

    assert response.content == "Hello from fake"
    assert response.model == "fake-model"


async def test_generate_builds_system_and_user_messages(
    service: LLMService, provider: FakeLLMProvider
) -> None:
    await service.generate("What is RAG?", system_prompt="Be concise.", temperature=0.2, max_tokens=50)

    call = provider.calls[0]
    assert call["messages"] == [
        ChatMessage(role="system", content="Be concise."),
        ChatMessage(role="user", content="What is RAG?"),
    ]
    assert call["temperature"] == 0.2
    assert call["max_tokens"] == 50


async def test_generate_without_system_prompt_sends_only_user_message(
    service: LLMService, provider: FakeLLMProvider
) -> None:
    await service.generate("Hi")

    assert provider.calls[0]["messages"] == [ChatMessage(role="user", content="Hi")]


async def test_generate_rejects_empty_prompt(service: LLMService, provider: FakeLLMProvider) -> None:
    with pytest.raises(AppError) as exc_info:
        await service.generate("   ")

    assert exc_info.value.code == "invalid_prompt"
    assert provider.calls == []
