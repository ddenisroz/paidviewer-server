"""add user_token is_active index

Revision ID: add_token_active_idx
Revises: e1bfe023c304
Create Date: 2025-01-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_token_active_idx'
down_revision: Union[str, None] = 'e1bfe023c304'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Добавляет составной индекс для ускорения запросов к активным токенам.
    
    Индекс покрывает наиболее частый паттерн запроса:
    WHERE user_id = X AND platform = Y AND is_active = True
    """
    op.create_index(
        'ix_user_tokens_active_lookup',
        'user_tokens',
        ['user_id', 'platform', 'is_active'],
        unique=False
    )


def downgrade() -> None:
    """Удаляет индекс при откате миграции."""
    op.drop_index('ix_user_tokens_active_lookup', table_name='user_tokens')

