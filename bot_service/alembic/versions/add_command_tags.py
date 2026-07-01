"""add_command_tags_field

Revision ID: add_command_tags
Revises: b911e0329ada
Create Date: 2025-01-05 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_command_tags'
down_revision: Union[str, Sequence[str], None] = '5676ba37b725'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add tags field to bot_commands table
    op.add_column('bot_commands', sa.Column('tags', sa.String(), nullable=True, default=''))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('bot_commands', 'tags')
