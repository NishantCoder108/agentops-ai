import uuid
from datetime import datetime

from pydantic import BaseModel


class MessageResponse(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime


class ConversationSummary(BaseModel):
    id: uuid.UUID
    created_at: datetime


class ConversationDetail(ConversationSummary):
    messages: list[MessageResponse]
