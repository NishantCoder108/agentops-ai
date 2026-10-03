import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.events import AgentDone, AgentEvent, AgentStatus, AgentToken, ClientDisconnected
from app.agent.service import AgentService
from app.api.dependencies import enforce_chat_rate_limit, get_agent_service
from app.core.exceptions import AppError
from app.models import Conversation, User
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.error import ErrorResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

_STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}


@router.post(
    "/chat",
    response_model=ChatResponse,
    response_model_exclude_none=True,
    summary="Send a message to the agent",
    responses={
        404: {"model": ErrorResponse, "description": "Conversation not found"},
        422: {"model": ErrorResponse, "description": "Invalid request"},
        429: {
            "model": ErrorResponse,
            "description": "Too many chat requests, or the LLM provider rate limit was exceeded",
        },
        503: {"model": ErrorResponse, "description": "Chat rate limit store is unavailable"},
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
    user: Annotated[User, Depends(enforce_chat_rate_limit)],
    agent: Annotated[AgentService, Depends(get_agent_service)],
) -> ChatResponse:
    session_factory: async_sessionmaker[AsyncSession] | None = request.app.state.db_session_factory
    if session_factory is None:
        result = await agent.run(payload.message)
        return ChatResponse(answer=result.answer, sources=result.sources, tools_used=result.tools_used)

    async with session_factory() as session:
        conversation_id = await _conversation_id(session, payload.conversation_id, user.id)
        result = await agent.run(payload.message, session=session, conversation_id=conversation_id)
        return ChatResponse(
            answer=result.answer,
            sources=result.sources,
            tools_used=result.tools_used,
            conversation_id=conversation_id,
            run_id=agent.run_id,
        )


@router.post(
    "/chat/stream",
    summary="Stream a message to the agent",
    response_class=StreamingResponse,
    responses={
        200: {"description": "Server-Sent Events: status, token, done, and error"},
        401: {"model": ErrorResponse, "description": "Missing or invalid access token"},
        403: {"model": ErrorResponse, "description": "Not allowed to chat"},
        404: {"model": ErrorResponse, "description": "Conversation not found"},
        422: {"model": ErrorResponse, "description": "Invalid request"},
        429: {"model": ErrorResponse, "description": "Too many chat requests"},
        503: {"model": ErrorResponse, "description": "Chat rate limit store is unavailable"},
    },
)
async def chat_stream(
    payload: ChatRequest,
    request: Request,
    user: Annotated[User, Depends(enforce_chat_rate_limit)],
    agent: Annotated[AgentService, Depends(get_agent_service)],
) -> StreamingResponse:
    """Stream agent status, tool progress, and answer tokens. POST /chat stays a single JSON response."""
    session_factory: async_sessionmaker[AsyncSession] | None = request.app.state.db_session_factory
    conversation_id: uuid.UUID | None = None
    if session_factory is not None:
        async with session_factory() as session:
            conversation_id = await _conversation_id(session, payload.conversation_id, user.id)
            await session.commit()

    return StreamingResponse(
        _sse_events(agent, payload.message, request, session_factory, conversation_id),
        media_type="text/event-stream",
        headers=_STREAM_HEADERS,
    )


async def _sse_events(
    agent: AgentService,
    message: str,
    request: Request,
    session_factory: async_sessionmaker[AsyncSession] | None,
    conversation_id: uuid.UUID | None,
) -> AsyncIterator[str]:
    if session_factory is None:
        async for chunk in _stream_session(agent, message, request, None, None):
            yield chunk
        return
    async with session_factory() as session:
        async for chunk in _stream_session(agent, message, request, session, conversation_id):
            yield chunk


async def _stream_session(
    agent: AgentService,
    message: str,
    request: Request,
    session: AsyncSession | None,
    conversation_id: uuid.UUID | None,
) -> AsyncIterator[str]:
    try:
        async for event in agent.stream(
            message,
            session=session,
            conversation_id=conversation_id,
            stop_when=request.is_disconnected,
        ):
            if await request.is_disconnected():
                break
            yield _encode(event, conversation_id=conversation_id, run_id=agent.run_id)
    except ClientDisconnected:
        return
    except AppError as exc:
        yield _sse("error", {"code": exc.code, "message": exc.message})
    except Exception:
        logger.exception("Chat stream failed")
        yield _sse("error", {"code": "agent_failed", "message": "The agent could not complete this request."})


def _encode(event: AgentEvent, *, conversation_id: uuid.UUID | None, run_id: uuid.UUID | None) -> str:
    if isinstance(event, AgentStatus):
        payload: dict[str, Any] = {"status": event.status}
        if event.tool is not None:
            payload["tool"] = event.tool
        return _sse("status", payload)
    if isinstance(event, AgentToken):
        return _sse("token", {"text": event.text, "replace": event.replace})
    if isinstance(event, AgentDone):
        body = ChatResponse(
            answer=event.response.answer,
            sources=event.response.sources,
            tools_used=event.response.tools_used,
            conversation_id=conversation_id,
            run_id=run_id,
        )
        return _sse("done", body.model_dump(mode="json", exclude_none=True))
    raise RuntimeError(f"Unexpected agent event {type(event)!r}")


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


async def _conversation_id(
    session: AsyncSession, conversation_id: uuid.UUID | None, user_id: uuid.UUID
) -> uuid.UUID:
    if conversation_id is not None:
        conversation = await session.get(Conversation, conversation_id)
        if conversation is None or conversation.user_id != user_id:
            raise AppError("Conversation not found", code="not_found", status_code=404)
        return conversation.id

    conversation = Conversation(user_id=user_id)
    session.add(conversation)
    await session.flush()
    return conversation.id
