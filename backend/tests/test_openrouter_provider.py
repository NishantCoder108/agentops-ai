import json
from collections.abc import Callable

import httpx2
import pytest

from app.llm import ChatMessage, LLMProviderError, ToolCall, ToolDefinition
from app.llm.providers.openrouter import OpenRouterProvider

pytestmark = pytest.mark.anyio

BASE_URL = "https://openrouter.test/api/v1"


def make_provider(handler: Callable[[httpx2.Request], httpx2.Response]) -> OpenRouterProvider:
    return OpenRouterProvider(
        api_key="test-key",
        model="test/model",
        base_url=BASE_URL,
        max_retries=0,
        app_name="AgentOps AI",
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )


def completion_body(content: str = "Hi there") -> dict:
    return {
        "id": "gen-1",
        "object": "chat.completion",
        "created": 0,
        "model": "test/model",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content},
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
    }


async def test_generate_sends_openai_compatible_request_and_parses_response() -> None:
    captured: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        captured.append(request)
        return httpx2.Response(200, json=completion_body())

    provider = make_provider(handler)
    response = await provider.generate(
        [ChatMessage(role="user", content="Hello")], temperature=0.1, max_tokens=20
    )
    await provider.aclose()

    request = captured[0]
    assert str(request.url) == f"{BASE_URL}/chat/completions"
    assert request.headers["authorization"] == "Bearer test-key"
    assert request.headers["x-title"] == "AgentOps AI"
    assert json.loads(request.content) == {
        "model": "test/model",
        "messages": [{"role": "user", "content": "Hello"}],
        "temperature": 0.1,
        "max_tokens": 20,
    }

    assert response.content == "Hi there"
    assert response.model == "test/model"
    assert response.finish_reason == "stop"
    assert response.usage is not None and response.usage.total_tokens == 8


async def test_generate_sends_tools_and_tool_messages_in_openai_format() -> None:
    captured: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        captured.append(request)
        return httpx2.Response(200, json=completion_body("It is 200."))

    call = ToolCall(id="call_1", name="calculator", arguments='{"expression": "25 * 800 / 100"}')
    tool = ToolDefinition(
        name="calculator",
        description="Evaluate arithmetic",
        parameters={"type": "object", "properties": {"expression": {"type": "string"}}},
    )
    provider = make_provider(handler)
    await provider.generate(
        [
            ChatMessage(role="user", content="25% of 800?"),
            ChatMessage(role="assistant", content=None, tool_calls=[call]),
            ChatMessage(role="tool", tool_call_id="call_1", content='{"result":200}'),
        ],
        tools=[tool],
    )
    await provider.aclose()

    body = json.loads(captured[0].content)
    assert body["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "calculator",
                "description": "Evaluate arithmetic",
                "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}},
            },
        }
    ]
    assert body["messages"] == [
        {"role": "user", "content": "25% of 800?"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "calculator", "arguments": '{"expression": "25 * 800 / 100"}'},
                }
            ],
        },
        {"role": "tool", "content": '{"result":200}', "tool_call_id": "call_1"},
    ]


async def test_generate_without_tools_omits_tools_field() -> None:
    captured: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        captured.append(request)
        return httpx2.Response(200, json=completion_body())

    provider = make_provider(handler)
    await provider.generate([ChatMessage(role="user", content="Hello")], tools=[])
    await provider.aclose()

    assert "tools" not in json.loads(captured[0].content)


async def test_generate_parses_tool_calls_from_response() -> None:
    body = completion_body()
    body["choices"][0]["finish_reason"] = "tool_calls"
    body["choices"][0]["message"] = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "calculator", "arguments": '{"expression": "2 + 2"}'},
            }
        ],
    }
    provider = make_provider(lambda _: httpx2.Response(200, json=body))

    response = await provider.generate([ChatMessage(role="user", content="2+2?")])
    await provider.aclose()

    assert response.content == ""
    assert response.finish_reason == "tool_calls"
    assert response.tool_calls == [
        ToolCall(id="call_1", name="calculator", arguments='{"expression": "2 + 2"}')
    ]


async def test_generate_maps_http_error_to_provider_error() -> None:
    provider = make_provider(lambda _: httpx2.Response(500, json={"error": {"message": "boom"}}))

    with pytest.raises(LLMProviderError) as exc_info:
        await provider.generate([ChatMessage(role="user", content="Hello")])

    assert exc_info.value.status_code == 502
    assert exc_info.value.details == {"provider_status": 500}


async def test_generate_maps_rate_limit_error() -> None:
    provider = make_provider(lambda _: httpx2.Response(429, json={"error": {"message": "slow down"}}))

    with pytest.raises(LLMProviderError) as exc_info:
        await provider.generate([ChatMessage(role="user", content="Hello")])

    assert exc_info.value.code == "llm_rate_limited"
    assert exc_info.value.status_code == 429
