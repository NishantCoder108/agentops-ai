import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent import DEFAULT_SYSTEM_PROMPT
from app.api import dependencies
from app.api.dependencies import get_llm_provider
from app.core.config import Settings
from app.llm import ChatMessage, LLMProviderError
from app.main import create_app
from app.schemas.chat import MAX_MESSAGE_LENGTH
from tests.conftest import make_settings
from tests.fakes import FakeLLMProvider


@pytest.fixture
def provider(app: FastAPI) -> FakeLLMProvider:
    fake = FakeLLMProvider(reply="Hi! How can I help?")
    app.dependency_overrides[get_llm_provider] = lambda: fake
    return fake


def test_chat_returns_agent_answer(client: TestClient, provider: FakeLLMProvider) -> None:
    response = client.post("/api/v1/chat", json={"message": "Hello"})

    assert response.status_code == 200
    assert response.json() == {"answer": "Hi! How can I help?"}


def test_chat_passes_message_to_provider(client: TestClient, provider: FakeLLMProvider) -> None:
    client.post("/api/v1/chat", json={"message": "  Hello  "})

    assert provider.calls[0]["messages"] == [
        ChatMessage(role="system", content=DEFAULT_SYSTEM_PROMPT),
        ChatMessage(role="user", content="Hello"),
    ]


@pytest.mark.parametrize(
    "body",
    [{}, {"message": ""}, {"message": "   "}, {"message": 123}, {"message": "x" * (MAX_MESSAGE_LENGTH + 1)}],
)
def test_chat_rejects_invalid_requests(
    client: TestClient, provider: FakeLLMProvider, body: dict
) -> None:
    response = client.post("/api/v1/chat", json=body)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert provider.calls == []


def test_chat_provider_error_uses_error_format(
    app: FastAPI, client: TestClient
) -> None:
    fake = FakeLLMProvider(error=LLMProviderError("LLM provider returned an error"))
    app.dependency_overrides[get_llm_provider] = lambda: fake

    response = client.post("/api/v1/chat", json={"message": "Hello"})

    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "code": "llm_provider_error",
            "message": "LLM provider returned an error",
            "details": None,
        }
    }


def test_chat_without_llm_config_returns_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    client = TestClient(create_app(make_settings()), raise_server_exceptions=False)

    response = client.post("/api/v1/chat", json={"message": "Hello"})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "llm_not_configured"


def test_provider_is_created_once_and_closed_on_shutdown(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    fake = FakeLLMProvider()
    created: list[Settings] = []

    def fake_factory(received: Settings) -> FakeLLMProvider:
        created.append(received)
        return fake

    monkeypatch.setattr(dependencies, "create_llm_provider", fake_factory)

    with TestClient(create_app(settings)) as client:
        client.post("/api/v1/chat", json={"message": "one"})
        client.post("/api/v1/chat", json={"message": "two"})
        assert fake.closed is False

    assert created == [settings]
    assert len(fake.calls) == 2
    assert fake.closed is True
