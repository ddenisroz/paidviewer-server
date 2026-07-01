"""add_tts_main_screen_settings

Revision ID: 20260518_tts_main_settings
Revises: 20260517_add_command_invocations
Create Date: 2026-05-18 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "20260518_tts_main_settings"
down_revision = "20260517_add_command_invocations"
branch_labels = None
depends_on = None


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {item["name"] for item in inspector.get_columns(table_name)}
    if column.name not in existing:
        op.add_column(table_name, column)


def _drop_column_if_exists(table_name: str, column_name: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {item["name"] for item in inspector.get_columns(table_name)}
    if column_name in existing:
        op.drop_column(table_name, column_name)


def upgrade() -> None:
    _add_column_if_missing("tts_user_settings", sa.Column("filter_banwords", sa.Boolean(), nullable=False, server_default=sa.true()))
    _add_column_if_missing("tts_user_settings", sa.Column("disable_voice_selection", sa.Boolean(), nullable=False, server_default=sa.false()))
    _add_column_if_missing("tts_user_settings", sa.Column("speak_sender_name", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    for column_name in (
        "speak_sender_name",
        "disable_voice_selection",
        "filter_banwords",
    ):
        _drop_column_if_exists("tts_user_settings", column_name)
