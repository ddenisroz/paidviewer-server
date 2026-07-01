"""merge heads for PostgreSQL migration chain

Revision ID: 52e4eb52e2e9
Revises: 0b29011760b6, 20251105_7tv_links_images
Create Date: 2025-11-05 23:00:54.254848

"""
from typing import Sequence, Union



# revision identifiers, used by Alembic.
revision: str = '52e4eb52e2e9'
down_revision: Union[str, None] = ('0b29011760b6', '20251105_7tv_links_images')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
