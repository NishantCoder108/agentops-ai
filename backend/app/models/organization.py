import uuid
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column

if TYPE_CHECKING:
    from app.models.commerce import Customer
    from app.models.conversation import Conversation
    from app.models.document import Document


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A tenant. Users and customers belong to exactly one organization."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200))

    users: Mapped[list["User"]] = relationship(back_populates="organization")
    customers: Mapped[list["Customer"]] = relationship(back_populates="organization")
    documents: Mapped[list["Document"]] = relationship(back_populates="organization")


class UserRole(StrEnum):
    ADMIN = "admin"
    USER = "user"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A member of an organization. `password_hash` is an Argon2 hash, never the password."""

    __tablename__ = "users"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[UserRole] = mapped_column(enum_column(UserRole, "role"), default=UserRole.USER)
    password_hash: Mapped[str] = mapped_column(String(255))

    organization: Mapped[Organization] = relationship(back_populates="users")
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
