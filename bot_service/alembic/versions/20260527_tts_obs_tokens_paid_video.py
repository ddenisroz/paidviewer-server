"""add dedicated TTS OBS tokens and paid video metadata

Revision ID: 20260527_tts_obs_paid_video
Revises: 20260523_add_drops_widget_sounds
Create Date: 2026-05-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260527_tts_obs_paid_video"
down_revision: Union[str, Sequence[str], None] = "20260523_add_drops_widget_sounds"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()

    with op.batch_alter_table("users") as batch_op:
        if not _column_exists(bind, "users", "tts_dock_token"):
            batch_op.add_column(sa.Column("tts_dock_token", sa.String(), nullable=True))
        if not _column_exists(bind, "users", "tts_source_token"):
            batch_op.add_column(sa.Column("tts_source_token", sa.String(), nullable=True))

    with op.batch_alter_table("youtube_queue") as batch_op:
        if not _column_exists(bind, "youtube_queue", "paid_source"):
            batch_op.add_column(sa.Column("paid_source", sa.String(), nullable=True))
        if not _column_exists(bind, "youtube_queue", "paid_amount"):
            batch_op.add_column(sa.Column("paid_amount", sa.Float(), nullable=True))
        if not _column_exists(bind, "youtube_queue", "paid_currency"):
            batch_op.add_column(sa.Column("paid_currency", sa.String(), nullable=True))
        if not _column_exists(bind, "youtube_queue", "source_alert_id"):
            batch_op.add_column(sa.Column("source_alert_id", sa.String(), nullable=True))

    if not _index_exists(bind, "youtube_queue", "ix_youtube_queue_source_alert_id"):
        op.create_index("ix_youtube_queue_source_alert_id", "youtube_queue", ["source_alert_id"])

    if _column_exists(bind, "drops_configs", "widget_spinning_duration_ms"):
        with op.batch_alter_table("drops_configs") as batch_op:
            batch_op.alter_column(
                "widget_spinning_duration_ms",
                existing_type=sa.Integer(),
                server_default="5000",
            )


def downgrade() -> None:
    bind = op.get_bind()

    if _index_exists(bind, "youtube_queue", "ix_youtube_queue_source_alert_id"):
        op.drop_index("ix_youtube_queue_source_alert_id", table_name="youtube_queue")

    with op.batch_alter_table("youtube_queue") as batch_op:
        if _column_exists(bind, "youtube_queue", "source_alert_id"):
            batch_op.drop_column("source_alert_id")
        if _column_exists(bind, "youtube_queue", "paid_currency"):
            batch_op.drop_column("paid_currency")
        if _column_exists(bind, "youtube_queue", "paid_amount"):
            batch_op.drop_column("paid_amount")
        if _column_exists(bind, "youtube_queue", "paid_source"):
            batch_op.drop_column("paid_source")

    with op.batch_alter_table("users") as batch_op:
        if _column_exists(bind, "users", "tts_source_token"):
            batch_op.drop_column("tts_source_token")
        if _column_exists(bind, "users", "tts_dock_token"):
            batch_op.drop_column("tts_dock_token")

    if _column_exists(bind, "drops_configs", "widget_spinning_duration_ms"):
        with op.batch_alter_table("drops_configs") as batch_op:
            batch_op.alter_column(
                "widget_spinning_duration_ms",
                existing_type=sa.Integer(),
                server_default="1500",
            )
