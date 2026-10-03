import uuid

from pydantic import BaseModel, Field


class Source(BaseModel):
    """A passage the knowledge tool returned and the answer cites."""

    document_id: uuid.UUID
    document_name: str
    relevant_excerpt: str


class AgentResponse(BaseModel):
    answer: str
    sources: list[Source] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
