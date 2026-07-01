"""add_message_fade_to_chatbox

Revision ID: 2b3c4d5e6f7g
Revises: 1a2b3c4d5e6f
Create Date: 2025-10-27 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2b3c4d5e6f7g'
down_revision = '1a2b3c4d5e6f'
branch_labels = None
depends_on = None


def upgrade():
    # Добавляем поле message_fade_seconds в chatbox_settings
    with op.batch_alter_table('chatbox_settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('message_fade_seconds', sa.Integer(), nullable=True, server_default='60'))


def downgrade():
    with op.batch_alter_table('chatbox_settings', schema=None) as batch_op:
        batch_op.drop_column('message_fade_seconds')

