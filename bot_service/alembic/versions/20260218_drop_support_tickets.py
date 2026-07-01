"""drop support ticket system tables

Revision ID: 20260218_drop_support_tickets
Revises: 20260217_add_memealerts_grants
Create Date: 2026-02-18 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260218_drop_support_tickets"
down_revision: Union[str, Sequence[str], None] = "20260217_add_memealerts_grants"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "ticket_responses"):
        op.drop_table("ticket_responses")
    if _table_exists(bind, "support_tickets"):
        op.drop_table("support_tickets")


def downgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, "support_tickets"):
        op.create_table(
            "support_tickets",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("user_name", sa.String(), nullable=False),
            sa.Column("user_email", sa.String(), nullable=True),
            sa.Column("subject", sa.String(), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'open'")),
            sa.Column("priority", sa.String(), nullable=False, server_default=sa.text("'medium'")),
            sa.Column("admin_notes", sa.Text(), nullable=True),
            sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("closed_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_support_tickets_user_id", "support_tickets", ["user_id"], unique=False)
        op.create_index("ix_support_tickets_status", "support_tickets", ["status"], unique=False)
        op.create_index("ix_support_tickets_created_at", "support_tickets", ["created_at"], unique=False)

    if not _table_exists(bind, "ticket_responses"):
        op.create_table(
            "ticket_responses",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("support_tickets.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("user_name", sa.String(), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("is_admin_response", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_ticket_responses_ticket_id", "ticket_responses", ["ticket_id"], unique=False)
        op.create_index("ix_ticket_responses_created_at", "ticket_responses", ["created_at"], unique=False)
