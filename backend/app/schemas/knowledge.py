import uuid

from pydantic import BaseModel, Field


class KnowledgeHit(BaseModel):
    document_id: uuid.UUID
    document: str
    chunk: str
    similarity: float = Field(ge=0, le=1)


class KnowledgeSearchResult(BaseModel):
    results: list[KnowledgeHit]


class DocumentResponse(BaseModel):
    id: str
    filename: str
    format: str
    chunk_count: int
