"""Add drops history event dedupe fields.

Revision ID: 20260330_drops_event_dedupe
Revises: 20260322_worker_control
Create Date: 2026-03-30 12:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260330_drops_event_dedupe"
down_revision: Union[str, Sequence[str], None] = "20260322_worker_control"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("drops_history", schema=None) as batch_op:
        batch_op.add_column(sa.Column("stream_session_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("source_event_id", sa.String(), nullable=True))
        batch_op.create_foreign_key(
            "fk_drops_history_stream_session",
            "stream_sessions",
            ["stream_session_id"],
            ["id"],
        )
        batch_op.create_index("ix_drops_history_stream_session_id", ["stream_session_id"])
        batch_op.create_index("ix_drops_history_source_event_id", ["source_event_id"])
        batch_op.create_unique_constraint(
            "uq_drops_history_user_source_event",
            ["user_id", "channel_name", "platform", "source_event_id"],
        )
        batch_op.create_unique_constraint(
            "uq_drops_history_session_source_event",
            ["session_id", "channel_name", "platform", "source_event_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("drops_history", schema=None) as batch_op:
        batch_op.drop_constraint("uq_drops_history_session_source_event", type_="unique")
        batch_op.drop_constraint("uq_drops_history_user_source_event", type_="unique")
        batch_op.drop_index("ix_drops_history_source_event_id")
        batch_op.drop_index("ix_drops_history_stream_session_id")
        batch_op.drop_constraint("fk_drops_history_stream_session", type_="foreignkey")
        batch_op.drop_column("source_event_id")
        batch_op.drop_column("stream_session_id")
