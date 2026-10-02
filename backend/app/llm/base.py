from collections.abc import Sequence
from typing import Protocol

from app.llm.types import ChatMessage, LLMResponse


class LLMProvider(Protocol):
    """Provider-agnostic interface for chat-style text generation.

    Implementations must translate provider-specific failures into `LLMError` subclasses.
    """

    name: str

    async def generate(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse: ...

    async def aclose(self) -> None: ...
