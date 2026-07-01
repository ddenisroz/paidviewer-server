"""make_user_id_nullable_in_bot_commands

Revision ID: 7f15d1d3ff0f
Revises: 7398efb7a962
Create Date: 2025-10-27 07:04:37.694061

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f15d1d3ff0f'
down_revision: Union[str, None] = '7398efb7a962'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite не поддерживает ALTER COLUMN, используем batch операцию
    with op.batch_alter_table('bot_commands', schema=None) as batch_op:
        batch_op.alter_column('user_id',
                              existing_type=sa.Integer(),
                              nullable=True)
        batch_op.alter_column('channel_name',
                              existing_type=sa.String(),
                              nullable=True)


def downgrade() -> None:
    # Откат: делаем поля обратно NOT NULL
    with op.batch_alter_table('bot_commands', schema=None) as batch_op:
        batch_op.alter_column('user_id',
                              existing_type=sa.Integer(),
                              nullable=False)
        batch_op.alter_column('channel_name',
                              existing_type=sa.String(),
                              nullable=False)
