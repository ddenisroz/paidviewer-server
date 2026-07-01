"""add user voice settings table

Revision ID: 20251031_user_voice_settings
Revises: 
Create Date: 2025-10-31 12:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251031_user_voice_settings'
down_revision = '3cbe5b9588a9'  # add_donationalerts_fields_to_users
branch_labels = None
depends_on = None


def upgrade():
    # Создаём таблицу user_voice_settings
    op.create_table(
        'user_voice_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('voice_id', sa.Integer(), nullable=False),
        sa.Column('voice_name', sa.String(), nullable=True),
        sa.Column('cfg_strength', sa.Float(), nullable=True),
        sa.Column('speed_preset', sa.String(), nullable=True),
        sa.Column('volume', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'voice_id', name='uq_user_voice')
    )
    op.create_index(op.f('ix_user_voice_settings_user_id'), 'user_voice_settings', ['user_id'], unique=False)


def downgrade():
    # Удаляем индекс и таблицу
    op.drop_index(op.f('ix_user_voice_settings_user_id'), table_name='user_voice_settings')
    op.drop_table('user_voice_settings')

