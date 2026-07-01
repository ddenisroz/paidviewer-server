"""remove voices table from bot_service (voices belong to tts_service only)

Revision ID: 20251031_remove_voices
Revises: 5723f1288b27
Create Date: 2025-10-31 14:00:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20251031_remove_voices'
down_revision: Union[str, None] = '5723f1288b27'  # merge_multiple_heads
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Удаляем таблицу voices из bot_service
    
    Голоса должны храниться ТОЛЬКО в tts_service database!
    Bot service использует UserVoiceSettings для персональных настроек.
    """
    from sqlalchemy import inspect

    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()

    if 'voices' in existing_tables:
        op.drop_table('voices')
        print("[OK] Удалена таблица 'voices' из bot_service (голоса хранятся в tts_service)")
    else:
        print("[INFO] Таблица 'voices' уже отсутствует")


def downgrade() -> None:
    """Восстановление таблицы voices (не рекомендуется)"""
    op.create_table('voices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('voice_type', sa.String(), nullable=True),
        sa.Column('file_path', sa.String(), nullable=False),
        sa.Column('reference_text', sa.String(), nullable=True),
        sa.Column('owner_id', sa.Integer(), nullable=True),
        sa.Column('is_public', sa.Boolean(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('cfg_strength', sa.Float(), nullable=True),
        sa.Column('speed_preset', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_index(op.f('ix_voices_id'), 'voices', ['id'], unique=False)
    op.create_index(op.f('ix_voices_name'), 'voices', ['name'], unique=True)

    print("[OK] Восстановлена таблица 'voices' (ВНИМАНИЕ: это legacy структура)")


