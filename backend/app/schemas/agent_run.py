import uuid
from datetime import datetime

from pydantic import BaseModel


class AgentRunToolResponse(BaseModel):
    tool_name: str
    status: str


class AgentRunResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    status: str
    started_at: datetime
    completed_at: datetime | None
    final_answer: str | None
    tool_calls: list[AgentRunToolResponse]
