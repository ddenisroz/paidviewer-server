"""add tri-state message background mode to chatbox settings

Revision ID: 20260527_chatbox_bg_modes
Revises: 20260527_chatbox_bg_mode
Create Date: 2026-05-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260527_chatbox_bg_modes"
down_revision: Union[str, Sequence[str], None] = "20260527_chatbox_bg_mode"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    if not _column_exists(bind, "chatbox_settings", "message_background_mode"):
        op.add_column(
            "chatbox_settings",
            sa.Column(
                "message_background_mode",
                sa.String(),
                nullable=False,
                server_default=sa.text("'message'"),
            ),
        )

    op.execute(
        sa.text(
            """
            UPDATE chatbox_settings
            SET message_background_mode = CASE
                WHEN separate_message_backgrounds = false THEN 'none'
                ELSE 'message'
            END
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    if _column_exists(bind, "chatbox_settings", "message_background_mode"):
        op.drop_column("chatbox_settings", "message_background_mode")
