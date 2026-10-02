import logging
from collections.abc import Sequence
from typing import Any

import httpx2
import openai
from openai import AsyncOpenAI

from app.llm.errors import LLMProviderError
from app.llm.types import ChatMessage, LLMResponse, TokenUsage

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider:
    """LLMProvider backed by OpenRouter's OpenAI-compatible chat completions API."""

    name = "openrouter"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
        app_name: str | None = None,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        self._model = model
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=max_retries,
            default_headers={"X-Title": app_name} if app_name else None,
            http_client=http_client,
        )

    async def generate(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        request: dict[str, Any] = {
            "model": model or self._model,
            "messages": [message.model_dump() for message in messages],
        }
        if temperature is not None:
            request["temperature"] = temperature
        if max_tokens is not None:
            request["max_tokens"] = max_tokens

        try:
            completion = await self._client.chat.completions.create(**request)
        except openai.APITimeoutError as exc:
            raise LLMProviderError(
                "LLM provider timed out", code="llm_timeout", status_code=504
            ) from exc
        except openai.RateLimitError as exc:
            raise LLMProviderError(
                "LLM provider rate limit exceeded", code="llm_rate_limited", status_code=429
            ) from exc
        except openai.APIStatusError as exc:
            logger.warning("OpenRouter returned HTTP %s: %s", exc.status_code, exc.message)
            raise LLMProviderError(
                "LLM provider returned an error",
                details={"provider_status": exc.status_code},
            ) from exc
        except openai.APIError as exc:
            logger.warning("OpenRouter request failed: %s", exc)
            raise LLMProviderError("Could not reach LLM provider") from exc

        if not completion.choices:
            raise LLMProviderError("LLM provider returned no choices")

        choice = completion.choices[0]
        usage = completion.usage
        return LLMResponse(
            content=choice.message.content or "",
            model=completion.model,
            finish_reason=choice.finish_reason,
            usage=TokenUsage(
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
            )
            if usage
            else None,
        )

    async def aclose(self) -> None:
        await self._client.close()
