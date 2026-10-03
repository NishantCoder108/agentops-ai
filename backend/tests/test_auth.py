import uuid

import pytest
from pydantic import ValidationError

from app.auth.errors import UnauthorizedError
from app.auth.passwords import hash_password, verify_password
from app.auth.permissions import Permission, permissions_for
from app.auth.tokens import create_access_token, decode_access_token
from app.models import UserRole
from tests.auth_helpers import JWT_SECRET
from tests.conftest import make_settings


def test_password_hash_is_not_the_password() -> None:
    password = "correct-horse-battery"
    stored = hash_password(password)

    assert stored != password
    assert password not in stored
    assert stored.startswith("$argon2")
    assert verify_password(password, stored) is True
    assert verify_password("wrong-password", stored) is False
    assert verify_password(password, "!") is False


def test_access_token_round_trip() -> None:
    settings = make_settings(jwt_secret=JWT_SECRET)
    user_id = uuid.uuid4()

    assert decode_access_token(settings, create_access_token(settings, user_id)) == user_id


def test_tampered_access_token_is_rejected() -> None:
    settings = make_settings(jwt_secret=JWT_SECRET)
    token = create_access_token(settings, uuid.uuid4())

    with pytest.raises(UnauthorizedError):
        decode_access_token(settings, token[:-4] + "abcd")


def test_short_jwt_secret_is_rejected() -> None:
    with pytest.raises(ValidationError, match="at least 32 characters"):
        make_settings(jwt_secret="too-short")


def test_roles_grant_only_their_own_permissions() -> None:
    admin = permissions_for(UserRole.ADMIN)
    user = permissions_for(UserRole.USER)

    assert admin == {
        Permission.MANAGE_DOCUMENTS,
        Permission.VIEW_AGENT_RUNS,
        Permission.MANAGE_USERS,
    }
    assert user == {Permission.CHAT, Permission.SEARCH_KNOWLEDGE, Permission.VIEW_OWN_CONVERSATIONS}
    assert admin.isdisjoint(user)
