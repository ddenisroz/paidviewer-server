"""remove_display_name_from_users

Revision ID: 78ee312b0e78
Revises: 4a2a8e4e2af1
Create Date: 2025-10-08 00:22:38.530148

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '78ee312b0e78'
down_revision: Union[str, None] = '4a2a8e4e2af1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Удаляем колонку display_name из таблицы users
    op.drop_column('users', 'display_name')


def downgrade() -> None:
    # Возвращаем колонку display_name (если нужно откатить)
    op.add_column('users', sa.Column('display_name', sa.String(), nullable=False))
