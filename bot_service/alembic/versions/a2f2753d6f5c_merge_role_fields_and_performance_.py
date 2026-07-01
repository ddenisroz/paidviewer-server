"""merge role fields and performance indexes

Revision ID: a2f2753d6f5c
Revises: 20251114_add_role_fields, add_performance_indexes
Create Date: 2025-11-15 02:36:48.196344

"""
from typing import Sequence, Union



# revision identifiers, used by Alembic.
revision: str = 'a2f2753d6f5c'
down_revision: Union[str, None] = ('20251114_add_role_fields', 'add_performance_indexes')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
