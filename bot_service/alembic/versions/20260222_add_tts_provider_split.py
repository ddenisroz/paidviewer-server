"""add provider split fields for advanced TTS

Revision ID: 20260222_add_tts_provider_split
Revises: 20260218_drop_support_tickets
Create Date: 2026-02-22 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260222_add_tts_provider_split"
down_revision: Union[str, Sequence[str], None] = "20260218_drop_support_tickets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(col.get("name") == column_name for col in inspector.get_columns(table_name))


def _get_unique_constraints(bind, table_name: str) -> list[dict]:
    inspector = sa.inspect(bind)
    try:
        return inspector.get_unique_constraints(table_name) or []
    except Exception:
        return []


def _has_index(bind, table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(bind)
    try:
        return any(idx.get("name") == index_name for idx in inspector.get_indexes(table_name))
    except Exception:
        return False


def _drop_unique_constraint_if_named(table_name: str, constraint_name: str) -> None:
    if not constraint_name:
        return
    op.drop_constraint(constraint_name, table_name, type_="unique")


def _drop_single_column_uniques(bind, table_name: str, target_columns: set[str]) -> None:
    for constraint in _get_unique_constraints(bind, table_name):
        name = constraint.get("name")
        columns = constraint.get("column_names") or []
        if len(columns) == 1 and columns[0] in target_columns:
            _drop_unique_constraint_if_named(table_name, name)


def _has_named_unique(bind, table_name: str, name: str) -> bool:
    return any((item.get("name") == name) for item in _get_unique_constraints(bind, table_name))


def _has_unique_columns(bind, table_name: str, expected_columns: list[str]) -> bool:
    for item in _get_unique_constraints(bind, table_name):
        if (item.get("column_names") or []) == expected_columns:
            return True
    return False


def upgrade() -> None:
    bind = op.get_bind()

    # ------------------------------------------------------------------
    # tts_user_settings: provider-aware advanced engine fields
    # ------------------------------------------------------------------
    if not _has_column(bind, "tts_user_settings", "advanced_provider"):
        op.add_column(
            "tts_user_settings",
            sa.Column("advanced_provider", sa.String(), nullable=False, server_default=sa.text("'f5'")),
        )
    if not _has_column(bind, "tts_user_settings", "f5_mode"):
        op.add_column(
            "tts_user_settings",
            sa.Column("f5_mode", sa.String(), nullable=False, server_default=sa.text("'cloud'")),
        )
    if not _has_column(bind, "tts_user_settings", "qwen_mode"):
        op.add_column(
            "tts_user_settings",
            sa.Column("qwen_mode", sa.String(), nullable=False, server_default=sa.text("'cloud'")),
        )
    if not _has_column(bind, "tts_user_settings", "qwen_voice"):
        op.add_column(
            "tts_user_settings",
            sa.Column("qwen_voice", sa.String(), nullable=False, server_default=sa.text("'default'")),
        )
    if not _has_column(bind, "tts_user_settings", "qwen_model"):
        op.add_column("tts_user_settings", sa.Column("qwen_model", sa.String(), nullable=True))

    # ------------------------------------------------------------------
    # local_tts_endpoints: split by provider + composite uniqueness
    # ------------------------------------------------------------------
    if not _has_column(bind, "local_tts_endpoints", "provider"):
        op.add_column(
            "local_tts_endpoints",
            sa.Column("provider", sa.String(), nullable=False, server_default=sa.text("'f5'")),
        )
    op.execute("UPDATE local_tts_endpoints SET provider = 'f5' WHERE provider IS NULL")

    if not _has_index(bind, "local_tts_endpoints", "ix_local_tts_endpoints_provider"):
        op.create_index("ix_local_tts_endpoints_provider", "local_tts_endpoints", ["provider"], unique=False)

    _drop_single_column_uniques(bind, "local_tts_endpoints", {"user_id", "session_id"})

    bind = op.get_bind()
    if not _has_named_unique(bind, "local_tts_endpoints", "uq_local_tts_endpoints_user_provider"):
        op.create_unique_constraint(
            "uq_local_tts_endpoints_user_provider",
            "local_tts_endpoints",
            ["user_id", "provider"],
        )
    if not _has_named_unique(bind, "local_tts_endpoints", "uq_local_tts_endpoints_session_provider"):
        op.create_unique_constraint(
            "uq_local_tts_endpoints_session_provider",
            "local_tts_endpoints",
            ["session_id", "provider"],
        )

    # ------------------------------------------------------------------
    # user_voice_settings: split by tts provider
    # ------------------------------------------------------------------
    if not _has_column(bind, "user_voice_settings", "tts_provider"):
        op.add_column(
            "user_voice_settings",
            sa.Column("tts_provider", sa.String(), nullable=False, server_default=sa.text("'f5'")),
        )
    op.execute("UPDATE user_voice_settings SET tts_provider = 'f5' WHERE tts_provider IS NULL")

    for constraint in _get_unique_constraints(bind, "user_voice_settings"):
        name = constraint.get("name")
        columns = constraint.get("column_names") or []
        if columns == ["user_id", "voice_id"]:
            _drop_unique_constraint_if_named("user_voice_settings", name)
        elif name == "uq_user_voice_settings" and columns != ["user_id", "voice_id", "tts_provider"]:
            _drop_unique_constraint_if_named("user_voice_settings", name)

    bind = op.get_bind()
    if not _has_unique_columns(bind, "user_voice_settings", ["user_id", "voice_id", "tts_provider"]):
        op.create_unique_constraint(
            "uq_user_voice_settings",
            "user_voice_settings",
            ["user_id", "voice_id", "tts_provider"],
        )


def downgrade() -> None:
    bind = op.get_bind()

    # user_voice_settings rollback
    if _has_named_unique(bind, "user_voice_settings", "uq_user_voice_settings"):
        op.drop_constraint("uq_user_voice_settings", "user_voice_settings", type_="unique")
    if _has_column(bind, "user_voice_settings", "tts_provider"):
        op.drop_column("user_voice_settings", "tts_provider")
    bind = op.get_bind()
    if not _has_unique_columns(bind, "user_voice_settings", ["user_id", "voice_id"]):
        op.create_unique_constraint("uq_user_voice_settings", "user_voice_settings", ["user_id", "voice_id"])

    # local_tts_endpoints rollback
    bind = op.get_bind()
    if _has_named_unique(bind, "local_tts_endpoints", "uq_local_tts_endpoints_user_provider"):
        op.drop_constraint("uq_local_tts_endpoints_user_provider", "local_tts_endpoints", type_="unique")
    if _has_named_unique(bind, "local_tts_endpoints", "uq_local_tts_endpoints_session_provider"):
        op.drop_constraint("uq_local_tts_endpoints_session_provider", "local_tts_endpoints", type_="unique")
    if _has_index(bind, "local_tts_endpoints", "ix_local_tts_endpoints_provider"):
        op.drop_index("ix_local_tts_endpoints_provider", table_name="local_tts_endpoints")
    if _has_column(bind, "local_tts_endpoints", "provider"):
        op.drop_column("local_tts_endpoints", "provider")
    bind = op.get_bind()
    if not _has_unique_columns(bind, "local_tts_endpoints", ["user_id"]):
        op.create_unique_constraint("uq_local_tts_endpoints_user_id", "local_tts_endpoints", ["user_id"])

    # tts_user_settings rollback
    if _has_column(bind, "tts_user_settings", "qwen_model"):
        op.drop_column("tts_user_settings", "qwen_model")
    if _has_column(bind, "tts_user_settings", "qwen_voice"):
        op.drop_column("tts_user_settings", "qwen_voice")
    if _has_column(bind, "tts_user_settings", "qwen_mode"):
        op.drop_column("tts_user_settings", "qwen_mode")
    if _has_column(bind, "tts_user_settings", "f5_mode"):
        op.drop_column("tts_user_settings", "f5_mode")
    if _has_column(bind, "tts_user_settings", "advanced_provider"):
        op.drop_column("tts_user_settings", "advanced_provider")
