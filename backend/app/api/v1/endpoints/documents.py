import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, UploadFile

from app.api.dependencies import get_current_organization_id, get_embedding_provider
from app.db.errors import DatabaseNotConfiguredError
from app.knowledge.embeddings import EmbeddingProvider
from app.knowledge.extract import document_format, extract_text, stored_filename
from app.knowledge.service import KnowledgeService
from app.schemas.error import ErrorResponse
from app.schemas.knowledge import DocumentResponse
from app.tools.knowledge import OrganizationNotConfiguredError

router = APIRouter(tags=["documents"])


@router.post(
    "/documents",
    response_model=DocumentResponse,
    status_code=201,
    summary="Upload a text or markdown document",
    responses={
        422: {"model": ErrorResponse, "description": "Invalid document"},
        500: {"model": ErrorResponse, "description": "Database or embeddings are not configured"},
        502: {"model": ErrorResponse, "description": "Embedding provider error"},
    },
)
async def create_document(
    file: UploadFile,
    request: Request,
    organization_id: Annotated[uuid.UUID | None, Depends(get_current_organization_id)],
    embedder: Annotated[EmbeddingProvider, Depends(get_embedding_provider)],
) -> DocumentResponse:
    if organization_id is None:
        raise OrganizationNotConfiguredError()
    session_factory = request.app.state.db_session_factory
    if session_factory is None:
        raise DatabaseNotConfiguredError()

    filename = stored_filename(file.filename or "")
    fmt = document_format(filename)
    text = extract_text(await file.read(), fmt)

    async with session_factory() as session:
        document = await KnowledgeService(session, organization_id, embedder).add_document(
            filename, fmt, text
        )
        chunk_count = len(document.chunks)
        return DocumentResponse(
            id=str(document.id),
            filename=document.filename,
            format=document.format.value,
            chunk_count=chunk_count,
        )
