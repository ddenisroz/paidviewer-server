"""Add command invocation history.

Revision ID: 20260517_add_command_invocations
Revises: 20260517_remove_qwen_tts_fields
Create Date: 2026-05-17 16:30:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260517_add_command_invocations"
down_revision: Union[str, Sequence[str], None] = "20260517_remove_qwen_tts_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "command_invocations"):
        return

    op.create_table(
        "command_invocations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("command_id", sa.Integer(), nullable=True),
        sa.Column("canonical_command_name", sa.String(), nullable=False),
        sa.Column("used_trigger", sa.String(), nullable=False),
        sa.Column("viewer_name", sa.String(), nullable=True),
        sa.Column("viewer_id", sa.String(), nullable=True),
        sa.Column("platform", sa.String(), nullable=False),
        sa.Column("channel_name", sa.String(), nullable=True),
        sa.Column("message_text", sa.Text(), nullable=True),
        sa.Column("chat_message_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="success"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["command_id"], ["bot_commands.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_command_invocations_id", "command_invocations", ["id"])
    op.create_index("ix_command_invocations_user_id", "command_invocations", ["user_id"])
    op.create_index("ix_command_invocations_command_id", "command_invocations", ["command_id"])
    op.create_index(
        "ix_command_invocations_canonical_command_name",
        "command_invocations",
        ["canonical_command_name"],
    )
    op.create_index("ix_command_invocations_used_trigger", "command_invocations", ["used_trigger"])
    op.create_index("ix_command_invocations_viewer_name", "command_invocations", ["viewer_name"])
    op.create_index("ix_command_invocations_viewer_id", "command_invocations", ["viewer_id"])
    op.create_index("ix_command_invocations_platform", "command_invocations", ["platform"])
    op.create_index("ix_command_invocations_channel_name", "command_invocations", ["channel_name"])
    op.create_index("ix_command_invocations_chat_message_id", "command_invocations", ["chat_message_id"])
    op.create_index("ix_command_invocations_status", "command_invocations", ["status"])
    op.create_index("ix_command_invocations_created_at", "command_invocations", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, "command_invocations"):
        return
    op.drop_table("command_invocations")
