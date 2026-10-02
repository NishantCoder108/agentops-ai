from collections.abc import Sequence
from typing import Any

from app.llm import ChatMessage, LLMResponse, ToolCall, ToolDefinition


class FakeLLMProvider:
    """In-memory LLMProvider for tests. Records calls and never touches the network.

    `responses` are returned in order, one per call; after they run out, every call returns `reply`.
    """

    name = "fake"

    def __init__(
        self,
        reply: str = "Hello from fake",
        error: Exception | None = None,
        responses: Sequence[LLMResponse] = (),
    ) -> None:
        self.reply = reply
        self.error = error
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    async def generate(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: Sequence[ToolDefinition] | None = None,
    ) -> LLMResponse:
        self.calls.append(
            {
                "messages": list(messages),
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "tools": list(tools) if tools is not None else None,
            }
        )
        if self.error is not None:
            raise self.error
        if self.responses:
            return self.responses.pop(0)
        return LLMResponse(content=self.reply, model=model or "fake-model")

    async def aclose(self) -> None:
        self.closed = True


def tool_call_response(*calls: ToolCall) -> LLMResponse:
    return LLMResponse(content="", model="fake-model", finish_reason="tool_calls", tool_calls=list(calls))


def answer_response(content: str) -> LLMResponse:
    return LLMResponse(content=content, model="fake-model", finish_reason="stop")
