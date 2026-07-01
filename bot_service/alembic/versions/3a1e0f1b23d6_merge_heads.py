"""merge_heads

Revision ID: 3a1e0f1b23d6
Revises: add_filtered_words, add_is_archived_to_support_tickets
Create Date: 2025-10-05 06:39:31.769731

"""
from typing import Sequence, Union



# revision identifiers, used by Alembic.
revision: str = '3a1e0f1b23d6'
down_revision: Union[str, None] = ('add_filtered_words', 'add_is_archived_to_support_tickets')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
