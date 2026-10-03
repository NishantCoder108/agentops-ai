import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin, enum_column
from app.models.conversation import Conversation


class AgentRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ToolCallStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentRun(UUIDPrimaryKeyMixin, Base):
    """One execution of the agent loop for a conversation.

    `started_at` is when the run began (before any tool call). Tool calls follow in `started_at`
    order. `final_answer` is set only when the run completes.
    """

    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(
            "(status = 'running') = (completed_at IS NULL)", name="completed_at_iff_finished"
        ),
        CheckConstraint(
            "(status = 'completed') = (final_answer IS NOT NULL)", name="final_answer_iff_completed"
        ),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[AgentRunStatus] = mapped_column(
        enum_column(AgentRunStatus, "status"), default=AgentRunStatus.RUNNING
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    final_answer: Mapped[str | None] = mapped_column(Text)

    conversation: Mapped[Conversation] = relationship(back_populates="runs")
    tool_calls: Mapped[list["ToolCall"]] = relationship(
        back_populates="agent_run",
        order_by="ToolCall.started_at",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ToolCall(UUIDPrimaryKeyMixin, Base):
    """One tool invocation inside an agent run. Arguments and results are JSON, never raw SQL."""

    __tablename__ = "tool_calls"
    __table_args__ = (
        CheckConstraint(
            "(status = 'running') = (completed_at IS NULL)", name="completed_at_iff_finished"
        ),
        CheckConstraint("(status = 'running') = (result IS NULL)", name="result_iff_finished"),
    )

    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    tool_name: Mapped[str] = mapped_column(String(64))
    arguments: Mapped[Any] = mapped_column(JSONB)
    result: Mapped[Any | None] = mapped_column(JSONB)
    status: Mapped[ToolCallStatus] = mapped_column(
        enum_column(ToolCallStatus, "status"), default=ToolCallStatus.RUNNING
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    agent_run: Mapped[AgentRun] = relationship(back_populates="tool_calls")
