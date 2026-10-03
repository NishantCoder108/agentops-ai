import uuid
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

MAX_MESSAGE_LENGTH = 8000


class ChatRequest(BaseModel):
    message: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MESSAGE_LENGTH),
        Field(examples=["Hello"]),
    ]
    conversation_id: uuid.UUID | None = None


class ChatResponse(BaseModel):
    answer: str
    conversation_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None
