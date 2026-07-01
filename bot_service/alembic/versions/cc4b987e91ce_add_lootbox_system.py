"""add_lootbox_system

Revision ID: cc4b987e91ce
Revises: 3a1e0f1b23d6
Create Date: 2025-10-05 06:40:15.423435

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cc4b987e91ce'
down_revision: Union[str, None] = '3a1e0f1b23d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Создаем таблицы для системы лутбоксов

    # LootboxType
    op.create_table('lootbox_types',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_lootbox_types_id'), 'lootbox_types', ['id'], unique=False)

    # LootboxQuality
    op.create_table('lootbox_qualities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('color', sa.String(), nullable=False),
        sa.Column('weight', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_lootbox_qualities_id'), 'lootbox_qualities', ['id'], unique=False)

    # LootboxConfig
    op.create_table('lootbox_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('channel_name', sa.String(), nullable=False),
        sa.Column('platform', sa.String(), nullable=False),
        sa.Column('streak_enabled', sa.Boolean(), nullable=True),
        sa.Column('streak_days_common', sa.Integer(), nullable=True),
        sa.Column('streak_days_rare', sa.Integer(), nullable=True),
        sa.Column('streak_days_epic', sa.Integer(), nullable=True),
        sa.Column('streak_days_legendary', sa.Integer(), nullable=True),
        sa.Column('streak_messages_required', sa.Integer(), nullable=True),
        sa.Column('donation_enabled', sa.Boolean(), nullable=True),
        sa.Column('donation_amount_common', sa.Float(), nullable=True),
        sa.Column('donation_amount_rare', sa.Float(), nullable=True),
        sa.Column('donation_amount_epic', sa.Float(), nullable=True),
        sa.Column('donation_amount_legendary', sa.Float(), nullable=True),
        sa.Column('mythical_enabled', sa.Boolean(), nullable=True),
        sa.Column('mythical_min_interval_hours', sa.Integer(), nullable=True),
        sa.Column('mythical_max_interval_hours', sa.Integer(), nullable=True),
        sa.Column('mythical_window_duration_minutes', sa.Integer(), nullable=True),
        sa.Column('mythical_donation_amount', sa.Float(), nullable=True),
        sa.Column('mythical_last_appeared', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_lootbox_configs_id'), 'lootbox_configs', ['id'], unique=False)
    op.create_index(op.f('ix_lootbox_configs_user_id'), 'lootbox_configs', ['user_id'], unique=False)
    op.create_index(op.f('ix_lootbox_configs_channel_name'), 'lootbox_configs', ['channel_name'], unique=False)

    # LootboxReward
    op.create_table('lootbox_rewards',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('channel_name', sa.String(), nullable=False),
        sa.Column('platform', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('quality_id', sa.Integer(), nullable=False),
        sa.Column('weight', sa.Integer(), nullable=True),
        sa.Column('reward_type', sa.String(), nullable=False),
        sa.Column('reward_value', sa.String(), nullable=False),
        sa.Column('sound_file', sa.String(), nullable=True),
        sa.Column('sound_volume', sa.Float(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['quality_id'], ['lootbox_qualities.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_lootbox_rewards_id'), 'lootbox_rewards', ['id'], unique=False)
    op.create_index(op.f('ix_lootbox_rewards_user_id'), 'lootbox_rewards', ['user_id'], unique=False)
    op.create_index(op.f('ix_lootbox_rewards_channel_name'), 'lootbox_rewards', ['channel_name'], unique=False)

    # UserStreak
    op.create_table('user_streaks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('channel_name', sa.String(), nullable=False),
        sa.Column('platform', sa.String(), nullable=False),
        sa.Column('viewer_id', sa.String(), nullable=False),
        sa.Column('viewer_name', sa.String(), nullable=False),
        sa.Column('current_streak', sa.Integer(), nullable=True),
        sa.Column('max_streak', sa.Integer(), nullable=True),
        sa.Column('last_activity', sa.DateTime(), nullable=True),
        sa.Column('messages_this_stream', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'viewer_id', 'platform', name='uq_user_streak')
    )
    op.create_index(op.f('ix_user_streaks_id'), 'user_streaks', ['id'], unique=False)
    op.create_index(op.f('ix_user_streaks_user_id'), 'user_streaks', ['user_id'], unique=False)
    op.create_index(op.f('ix_user_streaks_channel_name'), 'user_streaks', ['channel_name'], unique=False)
    op.create_index(op.f('ix_user_streaks_viewer_id'), 'user_streaks', ['viewer_id'], unique=False)

    # LootboxHistory
    op.create_table('lootbox_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('channel_name', sa.String(), nullable=False),
        sa.Column('platform', sa.String(), nullable=False),
        sa.Column('viewer_id', sa.String(), nullable=False),
        sa.Column('viewer_name', sa.String(), nullable=False),
        sa.Column('lootbox_type', sa.String(), nullable=False),
        sa.Column('quality_id', sa.Integer(), nullable=False),
        sa.Column('reward_id', sa.Integer(), nullable=True),
        sa.Column('reward_name', sa.String(), nullable=False),
        sa.Column('reward_type', sa.String(), nullable=False),
        sa.Column('reward_value', sa.String(), nullable=False),
        sa.Column('donation_amount', sa.Float(), nullable=True),
        sa.Column('streak_days', sa.Integer(), nullable=True),
        sa.Column('messages_count', sa.Integer(), nullable=True),
        sa.Column('donation_alert_id', sa.String(), nullable=True),
        sa.Column('chat_message_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['quality_id'], ['lootbox_qualities.id'], ),
        sa.ForeignKeyConstraint(['reward_id'], ['lootbox_rewards.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_lootbox_history_id'), 'lootbox_history', ['id'], unique=False)
    op.create_index(op.f('ix_lootbox_history_user_id'), 'lootbox_history', ['user_id'], unique=False)
    op.create_index(op.f('ix_lootbox_history_channel_name'), 'lootbox_history', ['channel_name'], unique=False)
    op.create_index(op.f('ix_lootbox_history_viewer_id'), 'lootbox_history', ['viewer_id'], unique=False)
    op.create_index(op.f('ix_lootbox_history_created_at'), 'lootbox_history', ['created_at'], unique=False)

    # MythicalLootboxSession
    op.create_table('mythical_lootbox_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('channel_name', sa.String(), nullable=False),
        sa.Column('platform', sa.String(), nullable=False),
        sa.Column('donation_amount', sa.Float(), nullable=False),
        sa.Column('window_duration_minutes', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('winner_viewer_id', sa.String(), nullable=True),
        sa.Column('winner_viewer_name', sa.String(), nullable=True),
        sa.Column('winner_donation_amount', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_mythical_lootbox_sessions_id'), 'mythical_lootbox_sessions', ['id'], unique=False)
    op.create_index(op.f('ix_mythical_lootbox_sessions_user_id'), 'mythical_lootbox_sessions', ['user_id'], unique=False)
    op.create_index(op.f('ix_mythical_lootbox_sessions_channel_name'), 'mythical_lootbox_sessions', ['channel_name'], unique=False)


def downgrade() -> None:
    # Удаляем таблицы в обратном порядке
    op.drop_index(op.f('ix_mythical_lootbox_sessions_channel_name'), table_name='mythical_lootbox_sessions')
    op.drop_index(op.f('ix_mythical_lootbox_sessions_user_id'), table_name='mythical_lootbox_sessions')
    op.drop_index(op.f('ix_mythical_lootbox_sessions_id'), table_name='mythical_lootbox_sessions')
    op.drop_table('mythical_lootbox_sessions')

    op.drop_index(op.f('ix_lootbox_history_created_at'), table_name='lootbox_history')
    op.drop_index(op.f('ix_lootbox_history_viewer_id'), table_name='lootbox_history')
    op.drop_index(op.f('ix_lootbox_history_channel_name'), table_name='lootbox_history')
    op.drop_index(op.f('ix_lootbox_history_user_id'), table_name='lootbox_history')
    op.drop_index(op.f('ix_lootbox_history_id'), table_name='lootbox_history')
    op.drop_table('lootbox_history')

    op.drop_index(op.f('ix_user_streaks_viewer_id'), table_name='user_streaks')
    op.drop_index(op.f('ix_user_streaks_channel_name'), table_name='user_streaks')
    op.drop_index(op.f('ix_user_streaks_user_id'), table_name='user_streaks')
    op.drop_index(op.f('ix_user_streaks_id'), table_name='user_streaks')
    op.drop_table('user_streaks')

    op.drop_index(op.f('ix_lootbox_rewards_channel_name'), table_name='lootbox_rewards')
    op.drop_index(op.f('ix_lootbox_rewards_user_id'), table_name='lootbox_rewards')
    op.drop_index(op.f('ix_lootbox_rewards_id'), table_name='lootbox_rewards')
    op.drop_table('lootbox_rewards')

    op.drop_index(op.f('ix_lootbox_configs_channel_name'), table_name='lootbox_configs')
    op.drop_index(op.f('ix_lootbox_configs_user_id'), table_name='lootbox_configs')
    op.drop_index(op.f('ix_lootbox_configs_id'), table_name='lootbox_configs')
    op.drop_table('lootbox_configs')

    op.drop_index(op.f('ix_lootbox_qualities_id'), table_name='lootbox_qualities')
    op.drop_table('lootbox_qualities')

    op.drop_index(op.f('ix_lootbox_types_id'), table_name='lootbox_types')
    op.drop_table('lootbox_types')
