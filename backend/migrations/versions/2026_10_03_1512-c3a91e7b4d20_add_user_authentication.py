"""add user authentication

Revision ID: c3a91e7b4d20
Revises: b7e2c4a91d08
Create Date: 2026-10-03 15:12:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3a91e7b4d20"
down_revision: str | None = "b7e2c4a91d08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing rows become ordinary users with a hash that cannot match any password.
    op.add_column(
        "users",
        sa.Column("role", sa.String(length=32), nullable=False, server_default="user"),
    )
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))
    op.execute("UPDATE users SET password_hash = '!' WHERE password_hash IS NULL")
    op.alter_column("users", "password_hash", nullable=False)
    op.create_check_constraint(op.f("ck_users_role"), "users", "role IN ('admin', 'user')")
    op.alter_column("users", "role", server_default=None)


def downgrade() -> None:
    op.drop_constraint(op.f("ck_users_role"), "users", type_="check")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "role")
