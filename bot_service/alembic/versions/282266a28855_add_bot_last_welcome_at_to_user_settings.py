"""add_bot_last_welcome_at_to_user_settings

Revision ID: 282266a28855
Revises: 02bdabb37f08
Create Date: 2025-10-29 10:12:57.991981

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '282266a28855'
down_revision: Union[str, None] = '02bdabb37f08'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем поле bot_last_welcome_at в таблицу user_settings
    op.add_column('user_settings',
        sa.Column('bot_last_welcome_at', sa.DateTime(), nullable=True)
    )


def downgrade() -> None:
    # Удаляем поле bot_last_welcome_at из таблицы user_settings
    op.drop_column('user_settings', 'bot_last_welcome_at')
