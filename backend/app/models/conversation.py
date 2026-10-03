import uuid
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin, enum_column
from app.models.organization import User

if TYPE_CHECKING:
    from app.models.agent_run import AgentRun


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class Conversation(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A chat thread owned by the user who started it."""

    __tablename__ = "conversations"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    user: Mapped[User | None] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        order_by="Message.created_at",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    runs: Mapped[list["AgentRun"]] = relationship(
        back_populates="conversation",
        order_by="AgentRun.started_at",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Message(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A user or assistant chat message. Messages are immutable, so there is no updated_at.

    Tool calls and their results are stored in `tool_calls`, linked through the agent run.
    """

    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation_id_created_at", "conversation_id", "created_at"),)

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    role: Mapped[MessageRole] = mapped_column(enum_column(MessageRole, "role"))
    content: Mapped[str] = mapped_column(Text)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
