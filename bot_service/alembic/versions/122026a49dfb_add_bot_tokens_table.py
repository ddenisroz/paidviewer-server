"""add_bot_tokens_table

Revision ID: 122026a49dfb
Revises: 20241218_remove_guest_mode
Create Date: 2025-12-18 04:28:11.312747

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '122026a49dfb'
down_revision: Union[str, None] = '20241218_remove_guest_mode'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Создаем таблицу bot_tokens для хранения токенов ботов с refresh_token
    op.create_table(
        'bot_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('platform', sa.String(), nullable=False),
        sa.Column('access_token', sa.String(), nullable=False),
        sa.Column('refresh_token', sa.String(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('scopes', sa.JSON(), nullable=True),
        sa.Column('bot_user_id', sa.String(), nullable=True),
        sa.Column('bot_login', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Создаем индексы
    op.create_index(op.f('ix_bot_tokens_platform'), 'bot_tokens', ['platform'], unique=True)


def downgrade() -> None:
    # Удаляем индексы
    op.drop_index(op.f('ix_bot_tokens_platform'), table_name='bot_tokens')
    
    # Удаляем таблицу
    op.drop_table('bot_tokens')
