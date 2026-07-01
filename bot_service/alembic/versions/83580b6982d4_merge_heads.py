"""merge_heads

Revision ID: 83580b6982d4
Revises: 852ca41d7915, e2cb097c43f0
Create Date: 2025-10-19 19:57:05.478191

"""
from typing import Sequence, Union



# revision identifiers, used by Alembic.
revision: str = '83580b6982d4'
down_revision: Union[str, None] = ('852ca41d7915', 'e2cb097c43f0')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
