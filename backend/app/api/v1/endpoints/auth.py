from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_app_settings, get_current_user, get_db_session
from app.auth.service import authenticate, register_organization
from app.core.config import Settings
from app.models import User
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserResponse, user_response
from app.schemas.error import ErrorResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=201,
    summary="Register an organization and its admin",
    responses={
        409: {"model": ErrorResponse, "description": "Email is already registered"},
        422: {"model": ErrorResponse, "description": "Invalid request"},
        500: {"model": ErrorResponse, "description": "Authentication or database is not configured"},
    },
)
async def register(
    payload: RegisterRequest,
    settings: Annotated[Settings, Depends(get_app_settings)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AuthResponse:
    user, token = await register_organization(session, settings, payload)
    return AuthResponse(access_token=token, user=user_response(user))


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Log in with email and password",
    responses={
        401: {"model": ErrorResponse, "description": "Invalid email or password"},
        422: {"model": ErrorResponse, "description": "Invalid request"},
        500: {"model": ErrorResponse, "description": "Authentication or database is not configured"},
    },
)
async def login(
    payload: LoginRequest,
    settings: Annotated[Settings, Depends(get_app_settings)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AuthResponse:
    user, token = await authenticate(session, settings, payload.email, payload.password)
    return AuthResponse(access_token=token, user=user_response(user))


@router.get(
    "/me",
    response_model=UserResponse,
    summary="The authenticated user",
    responses={401: {"model": ErrorResponse, "description": "Missing or invalid access token"}},
)
async def me(user: Annotated[User, Depends(get_current_user)]) -> UserResponse:
    return user_response(user)
