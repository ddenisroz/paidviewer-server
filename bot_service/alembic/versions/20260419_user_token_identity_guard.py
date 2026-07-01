"""Add a unique guard for linked OAuth identities.

Revision ID: 20260419_user_token_identity_guard
Revises: 20260330_drops_event_dedupe
Create Date: 2026-04-19 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260419_user_token_identity_guard"
down_revision: Union[str, Sequence[str], None] = "20260330_drops_event_dedupe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INDEX_NAME = "uq_user_tokens_platform_identity"


def _fail_on_duplicates() -> None:
    rows = op.get_bind().execute(
        sa.text(
            """
            SELECT platform, platform_user_id, COUNT(*) AS token_count
            FROM user_tokens
            WHERE user_id IS NOT NULL
              AND platform_user_id IS NOT NULL
              AND platform_user_id <> ''
            GROUP BY platform, platform_user_id
            HAVING COUNT(*) > 1
            LIMIT 10
            """
        )
    ).mappings().all()
    if rows:
        preview = ", ".join(
            f"{row['platform']}:{row['platform_user_id']} ({row['token_count']})"
            for row in rows
        )
        raise RuntimeError(
            "Duplicate user_tokens identities must be cleaned before applying "
            f"{INDEX_NAME}: {preview}"
        )


def upgrade() -> None:
    _fail_on_duplicates()
    op.create_index(
        INDEX_NAME,
        "user_tokens",
        ["platform", "platform_user_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
        sqlite_where=sa.text("user_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="user_tokens")
