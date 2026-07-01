"""add_streak_platform_flags_to_drops_config

Revision ID: 5765f2a789b9
Revises: 52e4eb52e2e9
Create Date: 2025-11-08 22:46:48.359234

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5765f2a789b9'
down_revision: Union[str, None] = '52e4eb52e2e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Добавляем новые поля для стрика (nullable=True сначала)
    op.add_column('drops_configs', sa.Column('streak_enabled_twitch', sa.Boolean(), nullable=True))
    op.add_column('drops_configs', sa.Column('streak_enabled_vk', sa.Boolean(), nullable=True))

    # 2. Делаем platform nullable
    op.alter_column('drops_configs', 'platform',
               existing_type=sa.VARCHAR(),
               nullable=True)

    # 3. Обновляем существующие данные:
    connection = op.get_bind()

    # Устанавливаем флаги для существующих записей на основе их platform и streak_enabled
    connection.execute(sa.text("""
        UPDATE drops_configs 
        SET streak_enabled_twitch = streak_enabled 
        WHERE platform = 'twitch' AND streak_enabled_twitch IS NULL
    """))

    connection.execute(sa.text("""
        UPDATE drops_configs 
        SET streak_enabled_vk = streak_enabled 
        WHERE platform = 'vk' AND streak_enabled_vk IS NULL
    """))

    # Устанавливаем дефолтные значения для остальных записей
    connection.execute(sa.text("""
        UPDATE drops_configs 
        SET streak_enabled_twitch = COALESCE(streak_enabled_twitch, false),
            streak_enabled_vk = COALESCE(streak_enabled_vk, false)
        WHERE streak_enabled_twitch IS NULL OR streak_enabled_vk IS NULL
    """))

    # 4. Устанавливаем NOT NULL и дефолтные значения для новых полей
    op.alter_column('drops_configs', 'streak_enabled_twitch',
               existing_type=sa.Boolean(),
               nullable=False,
               server_default='false')
    op.alter_column('drops_configs', 'streak_enabled_vk',
               existing_type=sa.Boolean(),
               nullable=False,
               server_default='false')

    # 5. Устанавливаем дефолтное значение для platform
    op.alter_column('drops_configs', 'platform',
               existing_type=sa.VARCHAR(),
               nullable=True,
               server_default='global')


def downgrade() -> None:
    # 1. Убираем дефолтные значения
    op.alter_column('drops_configs', 'platform',
               existing_type=sa.VARCHAR(),
               nullable=True,
               server_default=None)

    # 2. Удаляем новые поля
    op.drop_column('drops_configs', 'streak_enabled_vk')
    op.drop_column('drops_configs', 'streak_enabled_twitch')

    # 3. Восстанавливаем NOT NULL для platform
    # Устанавливаем "twitch" для записей с NULL platform или "global"
    connection = op.get_bind()
    connection.execute(sa.text("""
        UPDATE drops_configs 
        SET platform = 'twitch' 
        WHERE platform IS NULL OR platform = 'global'
    """))

    op.alter_column('drops_configs', 'platform',
               existing_type=sa.VARCHAR(),
               nullable=False)
