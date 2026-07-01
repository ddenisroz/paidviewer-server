"""add_chat_message_fade_seconds

Revision ID: 1a2b3c4d5e6f
Revises: 0c8f9a3b4d2e
Create Date: 2025-10-27 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1a2b3c4d5e6f'
down_revision = '0c8f9a3b4d2e'
branch_labels = None
depends_on = None


def upgrade():
    # Добавляем новое поле для времени исчезания сообщений
    with op.batch_alter_table('user_settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('chat_message_fade_seconds', sa.Integer(), nullable=True, server_default='60'))


def downgrade():
    with op.batch_alter_table('user_settings', schema=None) as batch_op:
        batch_op.drop_column('chat_message_fade_seconds')

