from app.core.exceptions import AppError
from app.llm.base import LLMProvider
from app.llm.types import ChatMessage, LLMResponse


class LLMService:
    """Application-facing text generation. Depends only on the LLMProvider interface."""

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        if not prompt.strip():
            raise AppError("Prompt must not be empty", code="invalid_prompt", status_code=422)

        messages: list[ChatMessage] = []
        if system_prompt:
            messages.append(ChatMessage(role="system", content=system_prompt))
        messages.append(ChatMessage(role="user", content=prompt))

        return await self._provider.generate(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
