import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.auth.errors import AuthNotConfiguredError, UnauthorizedError
from app.core.config import Settings

_ALGORITHM = "HS256"


def ensure_auth_configured(settings: Settings) -> None:
    _secret(settings)


def create_access_token(settings: Settings, user_id: uuid.UUID) -> str:
    secret = _secret(settings)
    expires = datetime.now(UTC) + timedelta(minutes=settings.jwt_access_token_minutes)
    return jwt.encode({"sub": str(user_id), "exp": expires}, secret, algorithm=_ALGORITHM)


def decode_access_token(settings: Settings, token: str) -> uuid.UUID:
    secret = _secret(settings)
    try:
        payload = jwt.decode(
            token, secret, algorithms=[_ALGORITHM], options={"require": ["exp", "sub"]}
        )
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError, TypeError):
        raise UnauthorizedError() from None


def _secret(settings: Settings) -> str:
    if settings.jwt_secret is None:
        raise AuthNotConfiguredError()
    return settings.jwt_secret.get_secret_value()
