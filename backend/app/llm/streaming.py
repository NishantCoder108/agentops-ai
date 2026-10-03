"""Normalize provider streaming and one-shot completions into the same sequence of parts."""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

from app.llm.base import LLMProvider
from app.llm.types import ChatMessage, LLMResponse, ToolDefinition


@dataclass(frozen=True)
class LLMStreamPart:
    """A piece of one model completion.

    `text` is a content delta. `tool_name` is set once, when a tool call's name is known.
    `response` is set on the final part and is the same shape `generate` would return.
    """

    text: str = ""
    tool_name: str | None = None
    response: LLMResponse | None = None


async def iterate_completion(
    provider: LLMProvider,
    messages: Sequence[ChatMessage],
    *,
    tools: Sequence[ToolDefinition] | None = None,
) -> AsyncIterator[LLMStreamPart]:
    """Stream when the provider supports it. Otherwise yield the completed response as one step."""
    stream = getattr(provider, "stream", None)
    if callable(stream):
        async for part in stream(messages, tools=tools):
            yield part
        return

    response = await provider.generate(messages, tools=tools)
    if response.content:
        yield LLMStreamPart(text=response.content)
    for call in response.tool_calls:
        yield LLMStreamPart(tool_name=call.name)
    yield LLMStreamPart(response=response)
