"""add_command_override_support

Revision ID: 7398efb7a962
Revises: 62aa67339537
Create Date: 2025-10-27 07:02:06.078339

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7398efb7a962'
down_revision: Union[str, None] = '62aa67339537'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем поле parent_command_id для связи override команд с глобальными
    op.add_column('bot_commands', sa.Column('parent_command_id', sa.Integer(), nullable=True))

    # Добавляем поле alias для пользовательских алиасов команд
    op.add_column('bot_commands', sa.Column('alias', sa.String(), nullable=True))

    # Изменяем command_type: добавляем новые типы 'global' и 'override'
    # Старые 'basic' -> 'global', 'custom' остается 'custom'
    # SQLite не поддерживает ALTER COLUMN, поэтому просто добавляем индекс
    op.create_index('idx_command_type', 'bot_commands', ['command_type'])

    # Добавляем индекс для parent_command_id для быстрого поиска
    op.create_index('idx_parent_command_id', 'bot_commands', ['parent_command_id'])

    # Добавляем составной индекс для быстрого поиска команд по user_id + command_name
    op.create_index('idx_user_command', 'bot_commands', ['user_id', 'command_name'])

    # Добавляем индекс для alias
    op.create_index('idx_alias', 'bot_commands', ['alias'])


def downgrade() -> None:
    # Удаляем индексы
    op.drop_index('idx_alias', table_name='bot_commands')
    op.drop_index('idx_user_command', table_name='bot_commands')
    op.drop_index('idx_parent_command_id', table_name='bot_commands')
    op.drop_index('idx_command_type', table_name='bot_commands')

    # Удаляем колонки
    op.drop_column('bot_commands', 'alias')
    op.drop_column('bot_commands', 'parent_command_id')
