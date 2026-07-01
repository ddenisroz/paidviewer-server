"""add separate message background mode to chatbox settings

Revision ID: 20260527_chatbox_bg_mode
Revises: 20260527_tts_obs_paid_video
Create Date: 2026-05-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260527_chatbox_bg_mode"
down_revision: Union[str, Sequence[str], None] = "20260527_tts_obs_paid_video"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    if not _column_exists(bind, "chatbox_settings", "separate_message_backgrounds"):
        op.add_column(
            "chatbox_settings",
            sa.Column(
                "separate_message_backgrounds",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _column_exists(bind, "chatbox_settings", "separate_message_backgrounds"):
        op.drop_column("chatbox_settings", "separate_message_backgrounds")
