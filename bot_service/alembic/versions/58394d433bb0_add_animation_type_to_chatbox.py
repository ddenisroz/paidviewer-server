"""add_animation_type_to_chatbox

Revision ID: 58394d433bb0
Revises: c1ec432a71d9
Create Date: 2025-10-23 11:32:32.180541

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '58394d433bb0'
down_revision: Union[str, None] = 'c1ec432a71d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем поле animation_type
    with op.batch_alter_table('chatbox_settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('animation_type', sa.String(), nullable=False, server_default='fade'))


def downgrade() -> None:
    # Откат изменений
    with op.batch_alter_table('chatbox_settings', schema=None) as batch_op:
        batch_op.drop_column('animation_type')
