from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.errors import EmailAlreadyRegisteredError, InvalidCredentialsError
from app.auth.passwords import hash_password, verify_password
from app.auth.tokens import create_access_token, ensure_auth_configured
from app.core.config import Settings
from app.models import Organization, User, UserRole
from app.schemas.auth import CreateUserRequest, RegisterRequest

# Verified when the email is unknown so that path takes about as long as a real password check.
_DUMMY_PASSWORD_HASH = hash_password("timing-only")


async def register_organization(session: AsyncSession, settings: Settings, data: RegisterRequest) -> tuple[User, str]:
    """Create a new organization and its first user, who is an admin."""
    ensure_auth_configured(settings)
    await _ensure_email_available(session, data.email)
    user = User(
        organization=Organization(name=data.organization_name),
        email=data.email,
        name=data.name,
        role=UserRole.ADMIN,
        password_hash=hash_password(data.password),
    )
    session.add(user)
    await _commit_user(session)
    return user, create_access_token(settings, user.id)


async def authenticate(session: AsyncSession, settings: Settings, email: str, password: str) -> tuple[User, str]:
    ensure_auth_configured(settings)
    user = await session.scalar(select(User).where(User.email == email))
    password_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    if user is None or not verify_password(password, password_hash):
        raise InvalidCredentialsError()
    return user, create_access_token(settings, user.id)


async def create_organization_user(session: AsyncSession, admin: User, data: CreateUserRequest) -> User:
    """Add a user to the admin's organization. The caller cannot choose a different organization."""
    await _ensure_email_available(session, data.email)
    user = User(
        organization_id=admin.organization_id,
        email=data.email,
        name=data.name,
        role=data.role,
        password_hash=hash_password(data.password),
    )
    session.add(user)
    await _commit_user(session)
    return user


async def _commit_user(session: AsyncSession) -> None:
    """A concurrent insert of the same email hits the unique constraint."""
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if getattr(exc.orig, "constraint_name", None) == "uq_users_email" or "uq_users_email" in str(exc):
            raise EmailAlreadyRegisteredError() from None
        raise


async def _ensure_email_available(session: AsyncSession, email: str) -> None:
    existing = await session.scalar(select(User.id).where(User.email == email))
    if existing is not None:
        raise EmailAlreadyRegisteredError()
