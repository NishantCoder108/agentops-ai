from typing import Literal

from pydantic import BaseModel

Role = Literal["system", "user", "assistant"]


class ChatMessage(BaseModel):
    role: Role
    content: str


class TokenUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class LLMResponse(BaseModel):
    content: str
    model: str
    finish_reason: str | None = None
    usage: TokenUsage | None = None
