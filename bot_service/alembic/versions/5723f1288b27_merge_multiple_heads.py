"""merge multiple heads

Revision ID: 5723f1288b27
Revises: 282266a28855, 20251031_user_voice_settings, 20251029_remove_unused
Create Date: 2025-10-31 11:44:51.675948

"""
from typing import Sequence, Union



# revision identifiers, used by Alembic.
revision: str = '5723f1288b27'
down_revision: Union[str, None] = ('282266a28855', '20251031_user_voice_settings', '20251029_remove_unused')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
