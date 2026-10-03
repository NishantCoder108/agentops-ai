from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agent.presentation import present_tool_call
from app.api.dependencies import get_db_session, require_permission
from app.auth.permissions import Permission
from app.models import AgentRun, Conversation, User
from app.schemas.agent_run import AgentRunResponse, AgentRunToolResponse
from app.schemas.error import ErrorResponse

router = APIRouter(prefix="/agent-runs", tags=["agent-runs"])


@router.get(
    "",
    response_model=list[AgentRunResponse],
    summary="List agent runs in the admin's organization",
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid access token"},
        403: {"model": ErrorResponse, "description": "Admin only"},
    },
)
async def list_agent_runs(
    admin: Annotated[User, Depends(require_permission(Permission.VIEW_AGENT_RUNS))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[AgentRunResponse]:
    rows = await session.scalars(
        select(AgentRun)
        .join(Conversation, AgentRun.conversation_id == Conversation.id)
        .join(User, Conversation.user_id == User.id)
        .where(User.organization_id == admin.organization_id)
        .options(selectinload(AgentRun.tool_calls))
        .order_by(AgentRun.started_at.desc())
        .limit(50)
    )
    return [
        AgentRunResponse(
            id=run.id,
            conversation_id=run.conversation_id,
            status=run.status.value,
            started_at=run.started_at,
            completed_at=run.completed_at,
            final_answer=run.final_answer,
            tool_calls=[
                AgentRunToolResponse.model_validate(
                    present_tool_call(
                        tool_name=call.tool_name,
                        status=call.status.value,
                        arguments=call.arguments,
                        result=call.result,
                        started_at=call.started_at,
                        completed_at=call.completed_at,
                    )
                )
                for call in run.tool_calls
            ],
        )
        for run in rows
    ]
