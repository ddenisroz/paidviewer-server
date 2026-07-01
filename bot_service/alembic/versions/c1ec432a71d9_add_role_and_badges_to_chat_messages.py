"""add_role_and_badges_to_chat_messages

Revision ID: c1ec432a71d9
Revises: 3cff2c951e93
Create Date: 2025-10-23 11:17:57.926109

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1ec432a71d9'
down_revision: Union[str, None] = '3cff2c951e93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем новые поля для ролей и значков
    with op.batch_alter_table('chat_messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('role', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('badges', sa.JSON(), nullable=True))


def downgrade() -> None:
    # Откат изменений
    with op.batch_alter_table('chat_messages', schema=None) as batch_op:
        batch_op.drop_column('badges')
        batch_op.drop_column('role')
