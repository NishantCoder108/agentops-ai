import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.service import AgentService
from app.api.dependencies import get_agent_service
from app.core.exceptions import AppError
from app.models import Conversation
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.error import ErrorResponse

router = APIRouter(tags=["chat"])


@router.post(
    "/chat",
    response_model=ChatResponse,
    response_model_exclude_none=True,
    summary="Send a message to the agent",
    responses={
        404: {"model": ErrorResponse, "description": "Conversation not found"},
        422: {"model": ErrorResponse, "description": "Invalid request"},
        429: {"model": ErrorResponse, "description": "LLM provider rate limit exceeded"},
        502: {
            "model": ErrorResponse,
            "description": "LLM provider error, or the agent did not finish within its step limit",
        },
        504: {"model": ErrorResponse, "description": "LLM provider timed out"},
    },
)
async def chat(
    payload: ChatRequest,
    request: Request,
    agent: Annotated[AgentService, Depends(get_agent_service)],
) -> ChatResponse:
    session_factory: async_sessionmaker[AsyncSession] | None = request.app.state.db_session_factory
    if session_factory is None:
        result = await agent.run(payload.message)
        return ChatResponse(answer=result.answer, sources=result.sources, tools_used=result.tools_used)

    async with session_factory() as session:
        conversation_id = await _conversation_id(session, payload.conversation_id)
        result = await agent.run(payload.message, session=session, conversation_id=conversation_id)
        return ChatResponse(
            answer=result.answer,
            sources=result.sources,
            tools_used=result.tools_used,
            conversation_id=conversation_id,
            run_id=agent.run_id,
        )


async def _conversation_id(session: AsyncSession, conversation_id: uuid.UUID | None) -> uuid.UUID:
    if conversation_id is not None:
        if await session.get(Conversation, conversation_id) is None:
            raise AppError("Conversation not found", code="not_found", status_code=404)
        return conversation_id

    conversation = Conversation()
    session.add(conversation)
    await session.flush()
    return conversation.id
