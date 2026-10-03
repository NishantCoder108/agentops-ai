"""track agent runs

Revision ID: a91c0e5d4b27
Revises: 4639b09fac61
Create Date: 2026-10-03 14:36:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a91c0e5d4b27"
down_revision: str | None = "4639b09fac61"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("conversations", "user_id", existing_type=sa.Uuid(), nullable=True)

    op.add_column("agent_runs", sa.Column("conversation_id", sa.Uuid(), nullable=True))
    op.execute(
        """
        UPDATE agent_runs AS run
        SET conversation_id = message.conversation_id
        FROM messages AS message
        WHERE message.id = run.input_message_id
        """
    )
    op.execute(
        "DELETE FROM tool_calls WHERE agent_run_id IN (SELECT id FROM agent_runs WHERE conversation_id IS NULL)"
    )
    op.execute("DELETE FROM agent_runs WHERE conversation_id IS NULL")
    op.alter_column("agent_runs", "conversation_id", nullable=False)
    op.create_foreign_key(
        op.f("fk_agent_runs_conversation_id_conversations"),
        "agent_runs",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(op.f("ix_agent_runs_conversation_id"), "agent_runs", ["conversation_id"])

    op.add_column(
        "agent_runs",
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
    )
    op.execute("UPDATE agent_runs SET started_at = created_at")
    op.alter_column("agent_runs", "started_at", nullable=False)
    op.add_column("agent_runs", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agent_runs", sa.Column("final_answer", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE agent_runs
        SET completed_at = updated_at,
            final_answer = CASE WHEN status = 'completed' THEN '' ELSE NULL END
        WHERE status <> 'running'
        """
    )

    op.drop_index(op.f("ix_agent_runs_input_message_id"), table_name="agent_runs")
    op.drop_constraint(op.f("ck_agent_runs_error_code_iff_failed"), "agent_runs", type_="check")
    op.drop_constraint(
        op.f("fk_agent_runs_input_message_id_messages"), "agent_runs", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_agent_runs_output_message_id_messages"), "agent_runs", type_="foreignkey"
    )
    op.drop_constraint(op.f("uq_agent_runs_output_message_id"), "agent_runs", type_="unique")
    op.drop_column("agent_runs", "input_message_id")
    op.drop_column("agent_runs", "output_message_id")
    op.drop_column("agent_runs", "model")
    op.drop_column("agent_runs", "error_code")
    op.drop_column("agent_runs", "created_at")
    op.drop_column("agent_runs", "updated_at")
    op.create_check_constraint(
        op.f("ck_agent_runs_completed_at_iff_finished"),
        "agent_runs",
        "(status = 'running') = (completed_at IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_agent_runs_final_answer_iff_completed"),
        "agent_runs",
        "(status = 'completed') = (final_answer IS NOT NULL)",
    )

    op.add_column("tool_calls", sa.Column("arguments_json", postgresql.JSONB(), nullable=True))
    op.execute(
        """
        CREATE OR REPLACE FUNCTION safe_jsonb(raw text) RETURNS jsonb AS $$
        BEGIN
            IF raw IS NULL OR btrim(raw) = '' THEN
                RETURN '{}'::jsonb;
            END IF;
            RETURN raw::jsonb;
        EXCEPTION WHEN others THEN
            RETURN jsonb_build_object('raw', raw);
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute("UPDATE tool_calls SET arguments_json = safe_jsonb(arguments)")
    op.execute("DROP FUNCTION safe_jsonb(text)")
    op.alter_column("tool_calls", "arguments_json", nullable=False)

    op.add_column("tool_calls", sa.Column("status", sa.String(length=32), nullable=True))
    op.execute(
        "UPDATE tool_calls SET status = CASE WHEN is_error THEN 'failed' ELSE 'completed' END"
    )
    op.alter_column("tool_calls", "status", nullable=False)
    op.create_check_constraint(
        op.f("ck_tool_calls_status"),
        "tool_calls",
        "status IN ('running', 'completed', 'failed')",
    )

    op.add_column(
        "tool_calls",
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
    )
    op.add_column("tool_calls", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE tool_calls SET started_at = created_at, completed_at = created_at")
    op.alter_column("tool_calls", "started_at", nullable=False)
    op.alter_column(
        "tool_calls", "result", existing_type=postgresql.JSONB(), nullable=True
    )

    op.drop_constraint(
        op.f("uq_tool_calls_agent_run_id_sequence"), "tool_calls", type_="unique"
    )
    op.drop_constraint(op.f("ck_tool_calls_sequence_positive"), "tool_calls", type_="check")
    op.drop_column("tool_calls", "sequence")
    op.drop_column("tool_calls", "arguments")
    op.drop_column("tool_calls", "is_error")
    op.drop_column("tool_calls", "created_at")
    op.alter_column("tool_calls", "arguments_json", new_column_name="arguments")
    op.create_index(op.f("ix_tool_calls_agent_run_id"), "tool_calls", ["agent_run_id"])
    op.create_check_constraint(
        op.f("ck_tool_calls_completed_at_iff_finished"),
        "tool_calls",
        "(status = 'running') = (completed_at IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_tool_calls_result_iff_finished"),
        "tool_calls",
        "(status = 'running') = (result IS NULL)",
    )


def downgrade() -> None:
    op.drop_table("tool_calls")
    op.drop_table("agent_runs")
    op.execute("DELETE FROM conversations WHERE user_id IS NULL")
    op.alter_column("conversations", "user_id", existing_type=sa.Uuid(), nullable=False)

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("input_message_id", sa.Uuid(), nullable=False),
        sa.Column("output_message_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')", name=op.f("ck_agent_runs_status")
        ),
        sa.CheckConstraint(
            "(status = 'failed') = (error_code IS NOT NULL)",
            name=op.f("ck_agent_runs_error_code_iff_failed"),
        ),
        sa.ForeignKeyConstraint(
            ["input_message_id"],
            ["messages.id"],
            name=op.f("fk_agent_runs_input_message_id_messages"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["output_message_id"],
            ["messages.id"],
            name=op.f("fk_agent_runs_output_message_id_messages"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_runs")),
        sa.UniqueConstraint("output_message_id", name=op.f("uq_agent_runs_output_message_id")),
    )
    op.create_index(op.f("ix_agent_runs_input_message_id"), "agent_runs", ["input_message_id"])

    op.create_table(
        "tool_calls",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.String(length=64), nullable=False),
        sa.Column("arguments", sa.Text(), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_error", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("sequence >= 1", name=op.f("ck_tool_calls_sequence_positive")),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["agent_runs.id"],
            name=op.f("fk_tool_calls_agent_run_id_agent_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tool_calls")),
        sa.UniqueConstraint(
            "agent_run_id", "sequence", name=op.f("uq_tool_calls_agent_run_id_sequence")
        ),
    )
