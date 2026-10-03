import uuid
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from app.models.organization import UserRole

_EMAIL = StringConstraints(strip_whitespace=True, min_length=3, max_length=320)
_NAME = StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
_PASSWORD = StringConstraints(min_length=8, max_length=128)


def _normalize_email(value: str) -> str:
    email = value.lower()
    if email.count("@") != 1:
        raise ValueError("Invalid email address")
    local, domain = email.split("@")
    if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise ValueError("Invalid email address")
    return email


EmailAddress = Annotated[str, _EMAIL, AfterValidator(_normalize_email)]
PersonName = Annotated[str, _NAME]
Password = Annotated[str, _PASSWORD]


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    email: EmailAddress
    name: PersonName
    password: Password
    organization_name: PersonName


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    email: EmailAddress
    password: Password


class CreateUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    email: EmailAddress
    name: PersonName
    password: Password
    role: UserRole = UserRole.USER


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    role: UserRole
    organization_id: uuid.UUID


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = Field(default="bearer")
    user: UserResponse


def user_response(user: object) -> UserResponse:
    return UserResponse.model_validate(user, from_attributes=True)
