"""add_platform_to_whitelisted_channels

Revision ID: ce4bd2fd04e4
Revises: dba42bf2f87e
Create Date: 2025-10-23 09:52:33.920921

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ce4bd2fd04e4'
down_revision: Union[str, None] = 'dba42bf2f87e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite не поддерживает ALTER COLUMN, поэтому используем batch операции
    with op.batch_alter_table('whitelisted_channels', schema=None) as batch_op:
        # Добавляем поле platform с дефолтным значением 'twitch'
        batch_op.add_column(sa.Column('platform', sa.String(), nullable=False, server_default='twitch'))

        # Создаем новый unique constraint для (channel_name, platform)
        batch_op.create_unique_constraint('uix_channel_platform', ['channel_name', 'platform'])


def downgrade() -> None:
    with op.batch_alter_table('whitelisted_channels', schema=None) as batch_op:
        # Удаляем unique constraint
        batch_op.drop_constraint('uix_channel_platform', type_='unique')

        # Удаляем поле platform
        batch_op.drop_column('platform')

        # Восстанавливаем старый unique constraint
        batch_op.create_unique_constraint('whitelisted_channels_channel_name_key', ['channel_name'])
