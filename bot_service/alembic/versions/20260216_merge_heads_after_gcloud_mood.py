"""merge alembic heads after gcloud mood migration

Revision ID: 20260216_merge_heads_gcloud
Revises: 20260216_add_gcloud_mood, 6ec6318c679f, add_extra_settings_cmd
Create Date: 2026-02-16 00:10:00.000000

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "20260216_merge_heads_gcloud"
down_revision: Union[str, Sequence[str], None] = (
    "20260216_add_gcloud_mood",
    "6ec6318c679f",
    "add_extra_settings_cmd",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
