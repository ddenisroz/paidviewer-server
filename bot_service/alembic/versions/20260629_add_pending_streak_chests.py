"""add pending streak chests

Revision ID: 20260629_pending_streak
Revises: 20260626_drop_w_style
Create Date: 2026-06-29 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260629_pending_streak"
down_revision = "20260626_drop_w_style"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pending_streak_chests",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("channel_name", sa.String(), nullable=False),
        sa.Column("platform", sa.String(), nullable=False),
        sa.Column("viewer_id", sa.String(), nullable=False),
        sa.Column("viewer_name", sa.String(), nullable=False),
        sa.Column("quality_id", sa.Integer(), sa.ForeignKey("drops_qualities.id"), nullable=False),
        sa.Column("quality_name", sa.String(), nullable=False),
        sa.Column("streak_days", sa.Integer(), nullable=False),
        sa.Column("messages_count", sa.Integer(), nullable=True),
        sa.Column("source_event_id", sa.String(), nullable=True),
        sa.Column("chat_message_id", sa.Integer(), nullable=True),
        sa.Column("stream_session_id", sa.Integer(), sa.ForeignKey("stream_sessions.id"), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("opened_history_id", sa.Integer(), sa.ForeignKey("drops_history.id"), nullable=True),
        sa.Column("opened_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "(user_id IS NOT NULL AND session_id IS NULL) OR (user_id IS NULL AND session_id IS NOT NULL)",
            name="check_user_or_session_pending_streak_chest",
        ),
    )
    op.create_index("ix_pending_streak_chests_user_id", "pending_streak_chests", ["user_id"])
    op.create_index("ix_pending_streak_chests_session_id", "pending_streak_chests", ["session_id"])
    op.create_index("ix_pending_streak_chests_viewer_id", "pending_streak_chests", ["viewer_id"])
    op.create_index("ix_pending_streak_chests_status", "pending_streak_chests", ["status"])
    op.create_index(
        "uq_pending_streak_chests_user_active",
        "pending_streak_chests",
        ["user_id", "channel_name", "platform", "viewer_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending' AND user_id IS NOT NULL"),
        sqlite_where=sa.text("status = 'pending' AND user_id IS NOT NULL"),
    )
    op.create_index(
        "uq_pending_streak_chests_session_active",
        "pending_streak_chests",
        ["session_id", "channel_name", "platform", "viewer_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending' AND session_id IS NOT NULL"),
        sqlite_where=sa.text("status = 'pending' AND session_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_pending_streak_chests_session_active", table_name="pending_streak_chests")
    op.drop_index("uq_pending_streak_chests_user_active", table_name="pending_streak_chests")
    op.drop_index("ix_pending_streak_chests_status", table_name="pending_streak_chests")
    op.drop_index("ix_pending_streak_chests_viewer_id", table_name="pending_streak_chests")
    op.drop_index("ix_pending_streak_chests_session_id", table_name="pending_streak_chests")
    op.drop_index("ix_pending_streak_chests_user_id", table_name="pending_streak_chests")
    op.drop_table("pending_streak_chests")
