"""remove_timestamps_add_roles_badges

Revision ID: 3cff2c951e93
Revises: ce4bd2fd04e4
Create Date: 2025-10-23 10:50:17.854811

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3cff2c951e93'
down_revision: Union[str, None] = 'ce4bd2fd04e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite не поддерживает ALTER COLUMN, поэтому используем batch операции
    with op.batch_alter_table('chatbox_settings', schema=None) as batch_op:
        # Добавляем новые поля
        batch_op.add_column(sa.Column('show_roles', sa.Boolean(), nullable=False, server_default='1'))
        batch_op.add_column(sa.Column('show_badges', sa.Boolean(), nullable=False, server_default='1'))

        # Удаляем старые поля (show_timestamps, timestamp_color)
        # SQLite требует batch mode для drop column
        batch_op.drop_column('show_timestamps')
        batch_op.drop_column('timestamp_color')


def downgrade() -> None:
    # Откат изменений
    with op.batch_alter_table('chatbox_settings', schema=None) as batch_op:
        # Возвращаем удалённые поля
        batch_op.add_column(sa.Column('show_timestamps', sa.Boolean(), nullable=False, server_default='1'))
        batch_op.add_column(sa.Column('timestamp_color', sa.String(), nullable=True, server_default='#808080'))

        # Удаляем добавленные поля
        batch_op.drop_column('show_roles')
        batch_op.drop_column('show_badges')
