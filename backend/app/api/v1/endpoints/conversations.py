import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_db_session, require_permission
from app.auth.permissions import Permission
from app.core.exceptions import AppError
from app.models import Conversation, User
from app.schemas.conversation import ConversationDetail, ConversationSummary, MessageResponse
from app.schemas.error import ErrorResponse

router = APIRouter(prefix="/conversations", tags=["conversations"])

_NOT_FOUND = {"model": ErrorResponse, "description": "Conversation not found"}


@router.get(
    "",
    response_model=list[ConversationSummary],
    summary="List the current user's conversations",
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid access token"},
        403: {"model": ErrorResponse, "description": "Not allowed to view conversations"},
    },
)
async def list_conversations(
    user: Annotated[User, Depends(require_permission(Permission.VIEW_OWN_CONVERSATIONS))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[ConversationSummary]:
    rows = await session.scalars(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.created_at.desc())
        .limit(50)
    )
    return [
        ConversationSummary(id=conversation.id, created_at=conversation.created_at) for conversation in rows
    ]


@router.get(
    "/{conversation_id}",
    response_model=ConversationDetail,
    summary="Read one of the current user's conversations",
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid access token"},
        403: {"model": ErrorResponse, "description": "Not allowed to view conversations"},
        404: _NOT_FOUND,
    },
)
async def get_conversation(
    conversation_id: uuid.UUID,
    user: Annotated[User, Depends(require_permission(Permission.VIEW_OWN_CONVERSATIONS))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ConversationDetail:
    conversation = await session.scalar(
        select(Conversation)
        .where(Conversation.id == conversation_id, Conversation.user_id == user.id)
        .options(selectinload(Conversation.messages))
    )
    if conversation is None:
        raise AppError("Conversation not found", code="not_found", status_code=404)
    return ConversationDetail(
        id=conversation.id,
        created_at=conversation.created_at,
        messages=[
            MessageResponse(
                id=message.id,
                role=message.role.value,
                content=message.content,
                created_at=message.created_at,
            )
            for message in conversation.messages
        ],
    )
