"""add drops widget style fields

Revision ID: 20260626_drop_w_style
Revises: 20260626_drop_w_start
Create Date: 2026-06-26 12:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260626_drop_w_style"
down_revision = "20260626_drop_w_start"
branch_labels = None
depends_on = None


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(column.get("name") == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    with op.batch_alter_table("drops_configs") as batch_op:
        if not _column_exists(bind, "drops_configs", "widget_frame_color"):
            batch_op.add_column(sa.Column("widget_frame_color", sa.String(length=32), nullable=True, server_default="#ff8a00"))
        if not _column_exists(bind, "drops_configs", "widget_text_color"):
            batch_op.add_column(sa.Column("widget_text_color", sa.String(length=32), nullable=True, server_default="#ffffff"))
        if not _column_exists(bind, "drops_configs", "widget_background_color"):
            batch_op.add_column(sa.Column("widget_background_color", sa.String(length=32), nullable=True, server_default="#120821"))
        if not _column_exists(bind, "drops_configs", "widget_font_scale"):
            batch_op.add_column(sa.Column("widget_font_scale", sa.Float(), nullable=True, server_default="1.0"))


def downgrade() -> None:
    bind = op.get_bind()
    with op.batch_alter_table("drops_configs") as batch_op:
        if _column_exists(bind, "drops_configs", "widget_font_scale"):
            batch_op.drop_column("widget_font_scale")
        if _column_exists(bind, "drops_configs", "widget_background_color"):
            batch_op.drop_column("widget_background_color")
        if _column_exists(bind, "drops_configs", "widget_text_color"):
            batch_op.drop_column("widget_text_color")
        if _column_exists(bind, "drops_configs", "widget_frame_color"):
            batch_op.drop_column("widget_frame_color")
