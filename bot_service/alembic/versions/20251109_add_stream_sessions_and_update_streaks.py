"""add_stream_sessions_and_update_streaks

Revision ID: 20251109_stream_sessions
Revises: 5765f2a789b9
Create Date: 2025-11-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20251109_stream_sessions'
down_revision: Union[str, None] = '5765f2a789b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Создаем таблицу stream_sessions для отслеживания трансляций
    op.create_table(
        'stream_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('session_id', sa.String(), nullable=True),
        sa.Column('channel_name', sa.String(), nullable=False),
        sa.Column('platform', sa.String(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('viewer_count_peak', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.CheckConstraint('(user_id IS NOT NULL AND session_id IS NULL) OR (user_id IS NULL AND session_id IS NOT NULL)', name='check_user_or_session_stream_session'),
        sa.PrimaryKeyConstraint('id')
    )

    # Создаем индексы для stream_sessions
    op.create_index('ix_stream_sessions_id', 'stream_sessions', ['id'])
    op.create_index('ix_stream_sessions_user_id', 'stream_sessions', ['user_id'])
    op.create_index('ix_stream_sessions_session_id', 'stream_sessions', ['session_id'])
    op.create_index('ix_stream_sessions_channel_name', 'stream_sessions', ['channel_name'])
    op.create_index('ix_stream_sessions_platform', 'stream_sessions', ['platform'])
    op.create_index('ix_stream_sessions_started_at', 'stream_sessions', ['started_at'])
    op.create_index('ix_stream_sessions_ended_at', 'stream_sessions', ['ended_at'])
    op.create_index('ix_stream_sessions_is_active', 'stream_sessions', ['is_active'])
    op.create_index('idx_stream_sessions_channel_platform_active', 'stream_sessions', ['channel_name', 'platform', 'is_active'])

    # Добавляем поля в user_streaks для отслеживания трансляций
    op.add_column('user_streaks', sa.Column('last_stream_session_id', sa.Integer(), nullable=True))
    op.add_column('user_streaks', sa.Column('last_stream_attended_at', sa.DateTime(), nullable=True))

    # Создаем внешний ключ для last_stream_session_id
    op.create_foreign_key(
        'fk_user_streaks_stream_session',
        'user_streaks',
        'stream_sessions',
        ['last_stream_session_id'],
        ['id']
    )

    # Создаем индексы для новых полей
    op.create_index('ix_user_streaks_last_stream_session_id', 'user_streaks', ['last_stream_session_id'])
    op.create_index('ix_user_streaks_last_stream_attended_at', 'user_streaks', ['last_stream_attended_at'])


def downgrade() -> None:
    # Удаляем индексы для новых полей в user_streaks
    op.drop_index('ix_user_streaks_last_stream_attended_at', table_name='user_streaks')
    op.drop_index('ix_user_streaks_last_stream_session_id', table_name='user_streaks')

    # Удаляем внешний ключ
    op.drop_constraint('fk_user_streaks_stream_session', 'user_streaks', type_='foreignkey')

    # Удаляем поля из user_streaks
    op.drop_column('user_streaks', 'last_stream_attended_at')
    op.drop_column('user_streaks', 'last_stream_session_id')

    # Удаляем индексы для stream_sessions
    op.drop_index('idx_stream_sessions_channel_platform_active', table_name='stream_sessions')
    op.drop_index('ix_stream_sessions_is_active', table_name='stream_sessions')
    op.drop_index('ix_stream_sessions_ended_at', table_name='stream_sessions')
    op.drop_index('ix_stream_sessions_started_at', table_name='stream_sessions')
    op.drop_index('ix_stream_sessions_platform', table_name='stream_sessions')
    op.drop_index('ix_stream_sessions_channel_name', table_name='stream_sessions')
    op.drop_index('ix_stream_sessions_session_id', table_name='stream_sessions')
    op.drop_index('ix_stream_sessions_user_id', table_name='stream_sessions')
    op.drop_index('ix_stream_sessions_id', table_name='stream_sessions')

    # Удаляем таблицу stream_sessions
    op.drop_table('stream_sessions')

