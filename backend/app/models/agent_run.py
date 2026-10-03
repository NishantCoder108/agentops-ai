import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.models.conversation import Message


class AgentRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One execution of the agent loop, triggered by a user message.

    The conversation is reachable through `input_message`, so it is not stored again. A user
    message can have several runs (e.g. retries); an assistant message is produced by at most one.
    """

    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint("(status = 'failed') = (error_code IS NOT NULL)", name="error_code_iff_failed"),
    )

    input_message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    output_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), unique=True
    )
    status: Mapped[AgentRunStatus] = mapped_column(
        enum_column(AgentRunStatus, "status"), default=AgentRunStatus.RUNNING
    )
    # Model identifier reported by the provider; unknown until the first LLM response.
    model: Mapped[str | None] = mapped_column(String(200))
    error_code: Mapped[str | None] = mapped_column(String(100))

    input_message: Mapped[Message] = relationship(foreign_keys=[input_message_id])
    output_message: Mapped[Message | None] = relationship(foreign_keys=[output_message_id])
    tool_calls: Mapped[list["ToolCall"]] = relationship(
        back_populates="agent_run",
        order_by="ToolCall.sequence",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ToolCall(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A tool invocation requested by the model during an agent run. Immutable once recorded."""

    __tablename__ = "tool_calls"
    __table_args__ = (
        # Also serves lookups by agent_run_id.
        UniqueConstraint("agent_run_id", "sequence"),
        CheckConstraint("sequence >= 1", name="sequence_positive"),
    )

    agent_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"))
    # 1-based execution order within the run; timestamps are not unique within a transaction.
    sequence: Mapped[int]
    tool_name: Mapped[str] = mapped_column(String(64))
    # Raw argument string exactly as the model produced it; it may be invalid JSON.
    arguments: Mapped[str] = mapped_column(Text)
    # The JSON returned to the model: the tool output, or {"error": ..., "details": ...}.
    result: Mapped[dict[str, Any]] = mapped_column(JSONB)
    is_error: Mapped[bool]

    agent_run: Mapped[AgentRun] = relationship(back_populates="tool_calls")
