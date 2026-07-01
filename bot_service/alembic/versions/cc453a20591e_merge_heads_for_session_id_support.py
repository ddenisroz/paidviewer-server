"""merge heads for session_id support

Revision ID: cc453a20591e
Revises: 20251031_remove_voices, 20251101_add_session_id
Create Date: 2025-11-01 14:22:04.626994

"""
from typing import Sequence, Union



# revision identifiers, used by Alembic.
revision: str = 'cc453a20591e'
down_revision: Union[str, None] = ('20251031_remove_voices', '20251101_add_session_id')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
