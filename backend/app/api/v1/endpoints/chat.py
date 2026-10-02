from typing import Annotated

from fastapi import APIRouter, Depends

from app.agent.service import AgentService
from app.api.dependencies import get_agent_service
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.error import ErrorResponse

router = APIRouter(tags=["chat"])


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Send a message to the agent",
    responses={
        422: {"model": ErrorResponse, "description": "Invalid request"},
        429: {"model": ErrorResponse, "description": "LLM provider rate limit exceeded"},
        502: {"model": ErrorResponse, "description": "LLM provider error"},
        504: {"model": ErrorResponse, "description": "LLM provider timed out"},
    },
)
async def chat(
    payload: ChatRequest, agent: Annotated[AgentService, Depends(get_agent_service)]
) -> ChatResponse:
    answer = await agent.run(payload.message)
    return ChatResponse(answer=answer)
