"""allow memealerts platform in user_tokens check constraint

Revision ID: 20260217_memalerts_ck
Revises: 20260216_merge_heads_gcloud
Create Date: 2026-02-17 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260217_memalerts_ck"
down_revision: Union[str, Sequence[str], None] = "20260216_merge_heads_gcloud"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _check_constraint_exists(bind, table_name: str, constraint_name: str) -> bool:
    inspector = sa.inspect(bind)
    try:
        constraints = inspector.get_check_constraints(table_name)
    except Exception:
        return False
    return any(constraint.get("name") == constraint_name for constraint in constraints)


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "user_tokens"):
        return

    if _check_constraint_exists(bind, "user_tokens", "ck_user_tokens_platform"):
        op.drop_constraint("ck_user_tokens_platform", "user_tokens", type_="check")

    op.create_check_constraint(
        "ck_user_tokens_platform",
        "user_tokens",
        "platform IN ('twitch', 'vk', 'donationalerts', 'memealerts')",
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "user_tokens"):
        return

    if _check_constraint_exists(bind, "user_tokens", "ck_user_tokens_platform"):
        op.drop_constraint("ck_user_tokens_platform", "user_tokens", type_="check")

    op.create_check_constraint(
        "ck_user_tokens_platform",
        "user_tokens",
        "platform IN ('twitch', 'vk', 'donationalerts')",
    )
