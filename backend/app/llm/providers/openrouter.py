import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx2
import openai
from openai import AsyncOpenAI

from app.llm.errors import LLMProviderError
from app.llm.streaming import LLMStreamPart
from app.llm.types import ChatMessage, LLMResponse, TokenUsage, ToolCall, ToolDefinition

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
        tools: Sequence[ToolDefinition] | None = None,
    ) -> LLMResponse:
        request = _request_body(
            model or self._model, messages, temperature=temperature, max_tokens=max_tokens, tools=tools
        )
        try:
            completion = await self._client.chat.completions.create(**request)
        except openai.APIError as exc:
            raise _provider_error(exc) from exc

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
            tool_calls=[
                ToolCall(id=call.id, name=call.function.name, arguments=call.function.arguments)
                for call in choice.message.tool_calls or []
                if call.type == "function"
            ],
        )

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: Sequence[ToolDefinition] | None = None,
    ) -> AsyncIterator[LLMStreamPart]:
        """Yield content deltas and tool names, then one part carrying the assembled response."""
        request = _request_body(
            model or self._model, messages, temperature=temperature, max_tokens=max_tokens, tools=tools
        )
        request["stream"] = True
        content: list[str] = []
        calls: dict[int, dict[str, str]] = {}
        announced: set[int] = set()
        finish_reason: str | None = None
        model_name = request["model"]
        try:
            chunks = await self._client.chat.completions.create(**request)
            async for chunk in chunks:
                if chunk.model:
                    model_name = chunk.model
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
                delta = choice.delta
                if delta is None:
                    continue
                if delta.content:
                    content.append(delta.content)
                    yield LLMStreamPart(text=delta.content)
                for tool_call in delta.tool_calls or []:
                    entry = calls.setdefault(tool_call.index, {"id": "", "name": "", "arguments": ""})
                    if tool_call.id:
                        entry["id"] = tool_call.id
                    function = tool_call.function
                    if function is not None:
                        if function.name:
                            entry["name"] += function.name
                        if function.arguments:
                            entry["arguments"] += function.arguments
                    if entry["name"] and tool_call.index not in announced:
                        announced.add(tool_call.index)
                        yield LLMStreamPart(tool_name=entry["name"])
        except openai.APIError as exc:
            raise _provider_error(exc) from exc

        if finish_reason is None and not content and not calls:
            raise LLMProviderError("LLM provider returned no choices")
        yield LLMStreamPart(
            response=LLMResponse(
                content="".join(content),
                model=model_name,
                finish_reason=finish_reason,
                tool_calls=[
                    ToolCall(
                        id=calls[index]["id"] or f"call_{index}",
                        name=calls[index]["name"],
                        arguments=calls[index]["arguments"],
                    )
                    for index in sorted(calls)
                ],
            )
        )

    async def aclose(self) -> None:
        await self._client.close()


def _request_body(
    model: str,
    messages: Sequence[ChatMessage],
    *,
    temperature: float | None,
    max_tokens: int | None,
    tools: Sequence[ToolDefinition] | None,
) -> dict[str, Any]:
    request: dict[str, Any] = {
        "model": model,
        "messages": [_to_openai_message(message) for message in messages],
    }
    if temperature is not None:
        request["temperature"] = temperature
    if max_tokens is not None:
        request["max_tokens"] = max_tokens
    if tools:
        request["tools"] = [_to_openai_tool(tool) for tool in tools]
    return request


def _provider_error(exc: openai.APIError) -> LLMProviderError:
    if isinstance(exc, openai.APITimeoutError):
        return LLMProviderError("LLM provider timed out", code="llm_timeout", status_code=504)
    if isinstance(exc, openai.RateLimitError):
        return LLMProviderError(
            "LLM provider rate limit exceeded", code="llm_rate_limited", status_code=429
        )
    if isinstance(exc, openai.APIStatusError):
        logger.warning("OpenRouter returned HTTP %s", exc.status_code)
        return LLMProviderError(
            "LLM provider returned an error",
            details={"provider_status": exc.status_code},
        )
    logger.warning("OpenRouter request failed: %s", type(exc).__name__)
    return LLMProviderError("Could not reach LLM provider")


def _to_openai_message(message: ChatMessage) -> dict[str, Any]:
    payload: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in message.tool_calls
        ]
    if message.tool_call_id is not None:
        payload["tool_call_id"] = message.tool_call_id
    return payload


def _to_openai_tool(tool: ToolDefinition) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }
