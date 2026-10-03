import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent import DEFAULT_SYSTEM_PROMPT
from app.api import dependencies
from app.api.dependencies import get_llm_provider
from app.core.config import Settings
from app.llm import ChatMessage, LLMProviderError, ToolCall
from app.main import create_app
from app.schemas.chat import MAX_MESSAGE_LENGTH
from tests.conftest import make_settings
from tests.fakes import FakeLLMProvider, answer_response, tool_call_response


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

    system, user = provider.calls[0]["messages"]
    assert system.role == "system" and system.content.startswith(DEFAULT_SYSTEM_PROMPT)
    assert user == ChatMessage(role="user", content="Hello")


def test_chat_offers_only_calculator_without_database(client: TestClient, provider: FakeLLMProvider) -> None:
    client.post("/api/v1/chat", json={"message": "Hello"})

    assert [tool.name for tool in provider.calls[0]["tools"]] == ["calculator"]


class _Session:
    """Enough of a database session to record a run without opening a connection."""

    def add(self, obj: object) -> None:
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()  # type: ignore[attr-defined]

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def get(self, model: object, key: object) -> None:
        return None

    async def __aenter__(self) -> "_Session":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


def _install_fake_database(app: FastAPI) -> None:
    app.state.db_session_factory = lambda: _Session()


def test_chat_offers_only_calculator_without_organization(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEFAULT_ORGANIZATION_ID", raising=False)
    app = create_app(make_settings(database_url="postgresql+asyncpg://u:p@127.0.0.1:1/none"))
    _install_fake_database(app)
    fake = FakeLLMProvider()
    app.dependency_overrides[get_llm_provider] = lambda: fake

    TestClient(app).post("/api/v1/chat", json={"message": "Hello"})

    assert [tool.name for tool in fake.calls[0]["tools"]] == ["calculator"]


def test_chat_offers_analytics_with_database_and_organization() -> None:
    # The tool is only offered here, never executed, so no database connection is opened.
    app = create_app(
        make_settings(
            database_url="postgresql+asyncpg://u:p@127.0.0.1:1/none",
            default_organization_id="7f1c7b7e-3c2e-4a59-9d39-2b0f5c3d8a10",
        )
    )
    _install_fake_database(app)
    fake = FakeLLMProvider()
    app.dependency_overrides[get_llm_provider] = lambda: fake

    TestClient(app).post("/api/v1/chat", json={"message": "Hello"})

    [calculator, analytics] = fake.calls[0]["tools"]
    assert (calculator.name, analytics.name) == ("calculator", "analytics")
    assert "organization" not in analytics.parameters["properties"]


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


def test_chat_runs_calculator_tool_and_returns_final_answer(app: FastAPI, client: TestClient) -> None:
    call = ToolCall(id="call_1", name="calculator", arguments='{"expression": "25 * 800 / 100"}')
    fake = FakeLLMProvider(responses=[tool_call_response(call), answer_response("25% of 800 is 200.")])
    app.dependency_overrides[get_llm_provider] = lambda: fake

    response = client.post("/api/v1/chat", json={"message": "What is 25% of 800?"})

    assert response.status_code == 200
    assert response.json() == {"answer": "25% of 800 is 200."}
    assert [tool.name for tool in fake.calls[0]["tools"]] == ["calculator"]
    assert fake.calls[1]["messages"][-1] == ChatMessage(
        role="tool", tool_call_id="call_1", content='{"result":200}'
    )


def test_chat_agent_step_limit_uses_error_format(app: FastAPI, client: TestClient) -> None:
    call = ToolCall(id="call_1", name="calculator", arguments='{"expression": "1 + 1"}')
    fake = FakeLLMProvider(responses=[tool_call_response(call)] * 10)
    app.dependency_overrides[get_llm_provider] = lambda: fake

    response = client.post("/api/v1/chat", json={"message": "Hello"})

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "agent_max_steps_exceeded"


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
