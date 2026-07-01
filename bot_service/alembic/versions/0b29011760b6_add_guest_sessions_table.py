"""add_guest_sessions_table

Revision ID: 0b29011760b6
Revises: 385b52d2dbf1
Create Date: 2025-11-05 17:48:36.758931

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0b29011760b6'
down_revision: Union[str, None] = '385b52d2dbf1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create guest_sessions table and migrate existing guest sessions from user_sessions"""

    # Создаем таблицу guest_sessions
    op.create_table(
        'guest_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.String(), nullable=False),
        sa.Column('channel_name', sa.String(), nullable=False),
        sa.Column('platform', sa.String(), nullable=False),
        sa.Column('device_info', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('last_activity', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Создаем индексы
    op.create_index('ix_guest_sessions_id', 'guest_sessions', ['id'])
    op.create_index('ix_guest_sessions_session_id', 'guest_sessions', ['session_id'], unique=True)
    op.create_index('ix_guest_sessions_channel_name', 'guest_sessions', ['channel_name'])
    op.create_index('ix_guest_sessions_created_at', 'guest_sessions', ['created_at'])
    op.create_index('ix_guest_sessions_last_activity', 'guest_sessions', ['last_activity'])
    op.create_index('ix_guest_sessions_is_active', 'guest_sessions', ['is_active'])
    op.create_index('idx_guest_channel_platform', 'guest_sessions', ['channel_name', 'platform'])

    # Мигрируем существующие гостевые сессии из user_sessions (user_id = -1)
    # ВАЖНО: Этот код будет выполнен только при upgrade, не при downgrade
    op.execute("""
        INSERT INTO guest_sessions (session_id, channel_name, platform, device_info, created_at, last_activity, is_active)
        SELECT 
            us.session_id,
            COALESCE(us.device_info->>'channel_name', 'unknown') as channel_name,
            COALESCE(us.device_info->>'platform', 'twitch') as platform,
            us.device_info,
            us.created_at,
            us.last_activity,
            us.is_active
        FROM user_sessions us
        WHERE us.user_id = -1
    """)

    # Удаляем гостевые сессии из user_sessions
    op.execute("DELETE FROM user_sessions WHERE user_id = -1")


def downgrade() -> None:
    """Remove guest_sessions table and restore guest sessions to user_sessions"""

    # Восстанавливаем гостевые сессии обратно в user_sessions
    # ВАЖНО: Нужно создать фиктивного пользователя с id=-1 для FK constraint
    # Или временно отключить FK constraint

    # Мигрируем данные обратно
    op.execute("""
        INSERT INTO user_sessions (user_id, session_id, device_info, created_at, last_activity, is_active)
        SELECT 
            -1 as user_id,
            gs.session_id,
            jsonb_set(
                COALESCE(gs.device_info, '{}'::jsonb),
                '{channel_name}',
                to_jsonb(gs.channel_name)
            ) as device_info,
            gs.created_at,
            gs.last_activity,
            gs.is_active
        FROM guest_sessions gs
    """)

    # Удаляем таблицу guest_sessions
    op.drop_index('idx_guest_channel_platform', table_name='guest_sessions')
    op.drop_index('ix_guest_sessions_is_active', table_name='guest_sessions')
    op.drop_index('ix_guest_sessions_last_activity', table_name='guest_sessions')
    op.drop_index('ix_guest_sessions_created_at', table_name='guest_sessions')
    op.drop_index('ix_guest_sessions_channel_name', table_name='guest_sessions')
    op.drop_index('ix_guest_sessions_session_id', table_name='guest_sessions')
    op.drop_index('ix_guest_sessions_id', table_name='guest_sessions')
    op.drop_table('guest_sessions')
