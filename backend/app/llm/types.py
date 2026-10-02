from typing import Any, Literal

from pydantic import BaseModel, Field

Role = Literal["system", "user", "assistant", "tool"]


class ToolCall(BaseModel):
    id: str
    name: str
    # Raw JSON string exactly as produced by the model; callers must validate it.
    arguments: str


class ChatMessage(BaseModel):
    role: Role
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None


class ToolDefinition(BaseModel):
    """A tool the model may call, described with a JSON Schema for its arguments."""

    name: str
    description: str
    parameters: dict[str, Any]


class TokenUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class LLMResponse(BaseModel):
    content: str
    model: str
    finish_reason: str | None = None
    usage: TokenUsage | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
