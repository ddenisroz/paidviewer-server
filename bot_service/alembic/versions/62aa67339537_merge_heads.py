"""merge_heads

Revision ID: 62aa67339537
Revises: 58394d433bb0, add_token_active_idx
Create Date: 2025-10-27 07:01:22.383142

"""
from typing import Sequence, Union



# revision identifiers, used by Alembic.
revision: str = '62aa67339537'
down_revision: Union[str, None] = ('58394d433bb0', 'add_token_active_idx')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
