"""add_tts_message_filters

Revision ID: 3c4d5e6f7g8h
Revises: 2b3c4d5e6f7g
Create Date: 2025-10-27 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3c4d5e6f7g8h'
down_revision = '2b3c4d5e6f7g'
branch_labels = None
depends_on = None


def upgrade():
    # Добавляем поля filter_replies и filter_mentions в tts_user_settings
    with op.batch_alter_table('tts_user_settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('filter_replies', sa.Boolean(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('filter_mentions', sa.Boolean(), nullable=False, server_default='0'))


def downgrade():
    with op.batch_alter_table('tts_user_settings', schema=None) as batch_op:
        batch_op.drop_column('filter_mentions')
        batch_op.drop_column('filter_replies')

