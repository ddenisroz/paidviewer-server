"""add drops widget sound settings

Revision ID: 20260523_add_drops_widget_sounds
Revises: 20260518_cleanup_tts_noise
Create Date: 2026-05-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260523_add_drops_widget_sounds"
down_revision: Union[str, Sequence[str], None] = "20260518_cleanup_tts_noise"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    with op.batch_alter_table("drops_configs") as batch_op:
        if not _column_exists(bind, "drops_configs", "widget_spin_sound_file"):
            batch_op.add_column(sa.Column("widget_spin_sound_file", sa.String(), nullable=True))
        if not _column_exists(bind, "drops_configs", "widget_reveal_sound_file"):
            batch_op.add_column(sa.Column("widget_reveal_sound_file", sa.String(), nullable=True))
        if not _column_exists(bind, "drops_configs", "widget_sound_volume"):
            batch_op.add_column(sa.Column("widget_sound_volume", sa.Float(), nullable=True, server_default="1.0"))


def downgrade() -> None:
    bind = op.get_bind()
    with op.batch_alter_table("drops_configs") as batch_op:
        if _column_exists(bind, "drops_configs", "widget_sound_volume"):
            batch_op.drop_column("widget_sound_volume")
        if _column_exists(bind, "drops_configs", "widget_reveal_sound_file"):
            batch_op.drop_column("widget_reveal_sound_file")
        if _column_exists(bind, "drops_configs", "widget_spin_sound_file"):
            batch_op.drop_column("widget_spin_sound_file")
