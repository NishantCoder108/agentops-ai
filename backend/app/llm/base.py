from collections.abc import Sequence
from typing import Protocol

from app.llm.types import ChatMessage, LLMResponse, ToolDefinition


class LLMProvider(Protocol):
    """Provider-agnostic interface for chat-style text generation.

    Implementations must translate provider-specific failures into `LLMError` subclasses.
    When `tools` are given, the model may answer with `LLMResponse.tool_calls` instead of content.
    """

    name: str

    async def generate(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: Sequence[ToolDefinition] | None = None,
    ) -> LLMResponse: ...

    async def aclose(self) -> None: ...
