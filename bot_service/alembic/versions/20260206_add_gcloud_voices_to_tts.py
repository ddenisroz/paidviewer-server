"""add gcloud voices to tts_user_settings

Revision ID: 20260206_add_gcloud_voices
Revises: 20260203_add_banned_status
Create Date: 2026-02-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "20260206_add_gcloud_voices"
down_revision = "20260203_add_banned_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tts_user_settings",
        sa.Column("gcloud_voices", sa.JSON(), nullable=False, server_default=sa.text("'[]'"))
    )
    op.alter_column("tts_user_settings", "gcloud_voices", server_default=None)


def downgrade() -> None:
    op.drop_column("tts_user_settings", "gcloud_voices")
