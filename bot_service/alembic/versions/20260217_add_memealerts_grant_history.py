"""add local memealerts grant history table

Revision ID: 20260217_add_memealerts_grants
Revises: 20260217_memalerts_ck
Create Date: 2026-02-17 01:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260217_add_memealerts_grants"
down_revision: Union[str, Sequence[str], None] = "20260217_memalerts_ck"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "memealerts_grant_history"):
        return

    op.create_table(
        "memealerts_grant_history",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("target_user_id", sa.String(), nullable=True),
        sa.Column("target_user_name", sa.String(), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column(
            "source", sa.String(), nullable=False, server_default=sa.text("'ui'")
        ),
        sa.Column(
            "platform",
            sa.String(),
            nullable=False,
            server_default=sa.text("'dashboard'"),
        ),
        sa.Column(
            "channel_name",
            sa.String(),
            nullable=False,
            server_default=sa.text("'dashboard'"),
        ),
        sa.Column("issued_by", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_memealerts_grant_history_user_id",
        "memealerts_grant_history",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_memealerts_grant_history_target_user_id",
        "memealerts_grant_history",
        ["target_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_memealerts_grant_history_target_user_name",
        "memealerts_grant_history",
        ["target_user_name"],
        unique=False,
    )
    op.create_index(
        "ix_memealerts_grant_history_created_at",
        "memealerts_grant_history",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "memealerts_grant_history"):
        return

    op.drop_table("memealerts_grant_history")
