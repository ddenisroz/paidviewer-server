"""add drops widget start sound

Revision ID: 20260626_drop_w_start
Revises: 20260523_add_drops_widget_sounds
Create Date: 2026-06-26 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260626_drop_w_start"
down_revision = "20260523_add_drops_widget_sounds"
branch_labels = None
depends_on = None


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = inspect(bind)
    return any(column.get("name") == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    with op.batch_alter_table("drops_configs") as batch_op:
        if not _column_exists(bind, "drops_configs", "widget_start_sound_file"):
            batch_op.add_column(sa.Column("widget_start_sound_file", sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    with op.batch_alter_table("drops_configs") as batch_op:
        if _column_exists(bind, "drops_configs", "widget_start_sound_file"):
            batch_op.drop_column("widget_start_sound_file")
