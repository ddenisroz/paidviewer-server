"""remove unused tables (MutedUser, TTSSettings, GuestVerification)

Revision ID: 20251029_remove_unused
Revises: (latest)
Create Date: 2025-10-29

Удаляет действительно неиспользуемые таблицы:
- muted_users (не используется, есть TTSBlockedUser)
- tts_settings (дубликат TTSUserSettings)
- guest_verifications (не реализовано для Twitch)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20251029_remove_unused'
down_revision: Union[str, None] = '7aa889f11a11'  # add_description_to_bot_commands (последняя миграция перед 29 октября)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Удаление неиспользуемых таблиц"""

    # Проверяем, существуют ли таблицы перед удалением
    from sqlalchemy import inspect

    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()

    # Удаляем только если таблица существует
    if 'muted_users' in existing_tables:
        op.drop_table('muted_users')
        print("[OK] Удалена таблица 'muted_users'")

    if 'tts_settings' in existing_tables:
        op.drop_table('tts_settings')
        print("[OK] Удалена таблица 'tts_settings'")

    if 'guest_verifications' in existing_tables:
        op.drop_table('guest_verifications')
        print("[OK] Удалена таблица 'guest_verifications'")

    print("\n[OK] Удаление неиспользуемых таблиц завершено")


def downgrade() -> None:
    """Восстановление таблиц (если нужно откатить)"""

    # muted_users
    op.create_table('muted_users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('channel_name', sa.String(), nullable=False),
        sa.Column('username', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_muted_users_id'), 'muted_users', ['id'], unique=False)
    op.create_index(op.f('ix_muted_users_channel_name'), 'muted_users', ['channel_name'], unique=False)
    op.create_index(op.f('ix_muted_users_username'), 'muted_users', ['username'], unique=False)

    # tts_settings
    op.create_table('tts_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tts_settings_id'), 'tts_settings', ['id'], unique=False)

    # guest_verifications
    op.create_table('guest_verifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('channel_name', sa.String(), nullable=False),
        sa.Column('verification_code', sa.String(), nullable=False),
        sa.Column('is_verified', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_guest_verifications_id'), 'guest_verifications', ['id'], unique=False)

    print("[OK] Восстановление таблиц завершено")

