from collections.abc import Sequence
from typing import Any

from app.llm import ChatMessage, LLMResponse


class FakeLLMProvider:
    """In-memory LLMProvider for tests. Records calls and never touches the network."""

    name = "fake"

    def __init__(self, reply: str = "Hello from fake", error: Exception | None = None) -> None:
        self.reply = reply
        self.error = error
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    async def generate(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self.calls.append(
            {
                "messages": list(messages),
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        if self.error is not None:
            raise self.error
        return LLMResponse(content=self.reply, model=model or "fake-model")

    async def aclose(self) -> None:
        self.closed = True
