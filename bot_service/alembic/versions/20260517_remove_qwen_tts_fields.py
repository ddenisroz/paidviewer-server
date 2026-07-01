"""Remove legacy Qwen TTS fields.

Revision ID: 20260517_remove_qwen_tts_fields
Revises: 20260419_user_token_identity_guard
Create Date: 2026-05-17 12:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260517_remove_qwen_tts_fields"
down_revision: Union[str, Sequence[str], None] = "20260419_user_token_identity_guard"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(col.get("name") == column_name for col in inspector.get_columns(table_name))


def _has_index(bind, table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(bind)
    try:
        return any(idx.get("name") == index_name for idx in inspector.get_indexes(table_name))
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()

    if _has_index(bind, "workers", "ix_workers_supports_qwen"):
        op.drop_index("ix_workers_supports_qwen", table_name="workers")
        bind = op.get_bind()

    if _has_column(bind, "workers", "supports_qwen"):
        op.drop_column("workers", "supports_qwen")
        bind = op.get_bind()

    if _has_column(bind, "tts_user_settings", "qwen_model"):
        op.drop_column("tts_user_settings", "qwen_model")
        bind = op.get_bind()

    if _has_column(bind, "tts_user_settings", "qwen_voice"):
        op.drop_column("tts_user_settings", "qwen_voice")
        bind = op.get_bind()

    if _has_column(bind, "tts_user_settings", "qwen_mode"):
        op.drop_column("tts_user_settings", "qwen_mode")


def downgrade() -> None:
    bind = op.get_bind()

    if not _has_column(bind, "tts_user_settings", "qwen_mode"):
        op.add_column(
            "tts_user_settings",
            sa.Column("qwen_mode", sa.String(), nullable=False, server_default=sa.text("'cloud'")),
        )
        bind = op.get_bind()

    if not _has_column(bind, "tts_user_settings", "qwen_voice"):
        op.add_column(
            "tts_user_settings",
            sa.Column("qwen_voice", sa.String(), nullable=False, server_default=sa.text("'default'")),
        )
        bind = op.get_bind()

    if not _has_column(bind, "tts_user_settings", "qwen_model"):
        op.add_column("tts_user_settings", sa.Column("qwen_model", sa.String(), nullable=True))
        bind = op.get_bind()

    if not _has_column(bind, "workers", "supports_qwen"):
        op.add_column(
            "workers",
            sa.Column("supports_qwen", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        bind = op.get_bind()

    if not _has_index(bind, "workers", "ix_workers_supports_qwen"):
        op.create_index("ix_workers_supports_qwen", "workers", ["supports_qwen"])
