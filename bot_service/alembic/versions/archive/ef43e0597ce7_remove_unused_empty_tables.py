"""remove_unused_empty_tables

Revision ID: ef43e0597ce7
Revises: 78ee312b0e78
Create Date: 2025-10-08 00:57:01.089461

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'ef43e0597ce7'
down_revision: Union[str, None] = '78ee312b0e78'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Удаляем пустые неиспользуемые таблицы
    empty_tables = [
        'muted_users',
        'blocked_channels',
        'vk_guest_verifications',
        'channel_points',
        'channel_rewards',
        'gambling_games',
        'points_transactions',
        'reward_queue',
        'gambling_results',
        'chat_messages',
        'user_progression',
        'achievements',
        'donation_alerts',
        'user_achievements',
        'psychology_analysis',
        'lootboxes'
    ]

    for table in empty_tables:
        op.drop_table(table)


def downgrade() -> None:
    # Восстанавливаем таблицы (если нужно откатить)
    # Пока оставляем пустым, так как эти таблицы не используются
    pass
