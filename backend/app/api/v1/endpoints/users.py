from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, require_permission
from app.auth.permissions import Permission
from app.auth.service import create_organization_user
from app.models import User
from app.schemas.auth import CreateUserRequest, UserResponse, user_response
from app.schemas.error import ErrorResponse

router = APIRouter(prefix="/users", tags=["users"])

_MAX_USERS = 200


@router.get(
    "",
    response_model=list[UserResponse],
    summary="List users in the admin's organization",
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid access token"},
        403: {"model": ErrorResponse, "description": "Admin only"},
    },
)
async def list_users(
    admin: Annotated[User, Depends(require_permission(Permission.MANAGE_USERS))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[UserResponse]:
    rows = await session.scalars(
        select(User)
        .where(User.organization_id == admin.organization_id)
        .order_by(User.created_at)
        .limit(_MAX_USERS)
    )
    return [user_response(user) for user in rows]


@router.post(
    "",
    response_model=UserResponse,
    status_code=201,
    summary="Create a user in the admin's organization",
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid access token"},
        403: {"model": ErrorResponse, "description": "Admin only"},
        409: {"model": ErrorResponse, "description": "Email is already registered"},
    },
)
async def create_user(
    payload: CreateUserRequest,
    admin: Annotated[User, Depends(require_permission(Permission.MANAGE_USERS))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserResponse:
    user = await create_organization_user(session, admin, payload)
    return user_response(user)
