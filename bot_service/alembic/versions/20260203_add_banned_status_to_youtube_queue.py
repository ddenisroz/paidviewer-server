"""allow banned status in youtube_queue

Revision ID: 20260203_add_banned_status
Revises: 20251218_fundamental
Create Date: 2026-02-03 06:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '20260203_add_banned_status'
down_revision = '20251218_fundamental'
branch_labels = None
depends_on = None


def _constraint_exists(conn, table_name: str, constraint_name: str) -> bool:
    result = conn.execute(
        sa.text(
            """
            SELECT 1
            FROM information_schema.table_constraints
            WHERE table_name = :table_name
              AND constraint_name = :constraint_name
            """
        ),
        {"table_name": table_name, "constraint_name": constraint_name},
    ).scalar()
    return bool(result)


def upgrade() -> None:
    conn = op.get_bind()
    if _constraint_exists(conn, "youtube_queue", "ck_youtube_queue_status"):
        op.drop_constraint("ck_youtube_queue_status", "youtube_queue", type_="check")
    op.create_check_constraint(
        "ck_youtube_queue_status",
        "youtube_queue",
        "status IN ('pending', 'playing', 'played', 'skipped', 'banned')",
    )


def downgrade() -> None:
    conn = op.get_bind()
    if _constraint_exists(conn, "youtube_queue", "ck_youtube_queue_status"):
        op.drop_constraint("ck_youtube_queue_status", "youtube_queue", type_="check")
    op.create_check_constraint(
        "ck_youtube_queue_status",
        "youtube_queue",
        "status IN ('pending', 'playing', 'played', 'skipped')",
    )
