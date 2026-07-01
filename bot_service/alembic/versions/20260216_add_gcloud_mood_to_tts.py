"""add gcloud mood to tts_user_settings

Revision ID: 20260216_add_gcloud_mood
Revises: 20260206_add_gcloud_voices
Create Date: 2026-02-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "20260216_add_gcloud_mood"
down_revision = "20260206_add_gcloud_voices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tts_user_settings",
        sa.Column("gcloud_mood", sa.String(length=32), nullable=False, server_default=sa.text("'neutral'")),
    )
    op.alter_column("tts_user_settings", "gcloud_mood", server_default=None)


def downgrade() -> None:
    op.drop_column("tts_user_settings", "gcloud_mood")
