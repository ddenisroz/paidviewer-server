"""cleanup_tts_settings_noise

Revision ID: 20260518_cleanup_tts_noise
Revises: 20260518_tts_main_settings
Create Date: 2026-05-18 00:10:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "20260518_cleanup_tts_noise"
down_revision = "20260518_tts_main_settings"
branch_labels = None
depends_on = None


def _drop_column_if_exists(table_name: str, column_name: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {item["name"] for item in inspector.get_columns(table_name)}
    if column_name in existing:
        op.drop_column(table_name, column_name)


def upgrade() -> None:
    for column_name in (
        "speak_symbols_and_emojis",
        "subscription_tts_enabled",
        "watch_streak_tts_enabled",
        "access_all",
        "access_subscribers",
        "access_vip",
        "access_moderators",
    ):
        _drop_column_if_exists("tts_user_settings", column_name)

    op.alter_column(
        "tts_user_settings",
        "enabled_platforms",
        server_default=sa.text("'[]'::json"),
        existing_type=sa.JSON(),
    )


def downgrade() -> None:
    op.alter_column(
        "tts_user_settings",
        "enabled_platforms",
        server_default=sa.text("'[\"twitch\", \"vk\"]'::json"),
        existing_type=sa.JSON(),
    )
