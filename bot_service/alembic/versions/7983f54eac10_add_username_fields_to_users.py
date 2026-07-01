"""add_username_fields_to_users

Revision ID: 7983f54eac10
Revises: 7aa889f11a11
Create Date: 2025-10-10 07:19:51.359236

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7983f54eac10'
down_revision: Union[str, None] = '7aa889f11a11'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем поля для username'ов платформ
    op.add_column('users', sa.Column('twitch_username', sa.String(), nullable=True))
    op.add_column('users', sa.Column('vk_username', sa.String(), nullable=True))
    op.add_column('users', sa.Column('is_active', sa.Boolean(), nullable=True, default=True))


def downgrade() -> None:
    # Удаляем добавленные поля
    op.drop_column('users', 'is_active')
    op.drop_column('users', 'vk_username')
    op.drop_column('users', 'twitch_username')
