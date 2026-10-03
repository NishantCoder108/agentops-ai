import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_llm_provider
from app.llm import LLMProviderError, ToolCall
from app.main import create_app
from tests.auth_helpers import install_user
from tests.conftest import make_settings
from tests.fakes import FakeLLMProvider, answer_response, tool_call_response


@pytest.fixture(autouse=True)
def authenticated_user(app: FastAPI):
    return install_user(app)


@pytest.fixture
def provider(app: FastAPI) -> FakeLLMProvider:
    fake = FakeLLMProvider(reply="Hi! How can I help?")
    app.dependency_overrides[get_llm_provider] = lambda: fake
    return fake


def _events(body: str) -> list[tuple[str, dict]]:
    parsed: list[tuple[str, dict]] = []
    for block in body.split("\n\n"):
        if not block.strip():
            continue
        event_name = "message"
        data = ""
        for line in block.split("\n"):
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = line.split(":", 1)[1].strip()
        parsed.append((event_name, json.loads(data)))
    return parsed


def test_chat_stream_sends_status_tokens_and_the_final_answer(
    client: TestClient, provider: FakeLLMProvider
) -> None:
    response = client.post("/api/v1/chat/stream", json={"message": "Hello"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response.text)
    assert events[0] == ("status", {"status": "thinking"})
    assert ("status", {"status": "generating"}) in events
    assert ("token", {"text": "Hi! How can I help?", "replace": False}) in events
    name, done = events[-1]
    assert name == "done"
    assert done["answer"] == "Hi! How can I help?"
    assert done["sources"] == []
    assert done["tools_used"] == []
    assert provider.calls


def test_chat_stream_reports_a_tool_then_the_answer(client: TestClient, provider: FakeLLMProvider) -> None:
    provider.responses = [
        tool_call_response(ToolCall(id="call_1", name="calculator", arguments='{"expression": "2 + 2"}')),
        answer_response("4"),
    ]

    response = client.post("/api/v1/chat/stream", json={"message": "What is 2 + 2?"})

    events = _events(response.text)
    assert ("status", {"status": "tool", "tool": "calculator"}) in events
    assert ("status", {"status": "generating"}) in events
    done = events[-1][1]
    assert done["answer"] == "4"
    assert done["tools_used"] == ["calculator"]


def test_chat_stream_reports_provider_timeout(client: TestClient, provider: FakeLLMProvider) -> None:
    provider.error = LLMProviderError("LLM provider timed out", code="llm_timeout", status_code=504)

    response = client.post("/api/v1/chat/stream", json={"message": "Hello"})

    assert response.status_code == 200
    events = _events(response.text)
    assert events[-1] == ("error", {"code": "llm_timeout", "message": "LLM provider timed out"})


def test_chat_stream_without_a_token_is_unauthorized() -> None:
    app = create_app(make_settings())
    fake = FakeLLMProvider()
    app.dependency_overrides[get_llm_provider] = lambda: fake

    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/chat/stream", json={"message": "Hello"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert fake.calls == []


def test_json_chat_endpoint_is_unchanged(client: TestClient, provider: FakeLLMProvider) -> None:
    response = client.post("/api/v1/chat", json={"message": "Hello"})

    assert response.status_code == 200
    assert response.json() == {"answer": "Hi! How can I help?", "sources": [], "tools_used": []}
    assert "event:" not in response.text
