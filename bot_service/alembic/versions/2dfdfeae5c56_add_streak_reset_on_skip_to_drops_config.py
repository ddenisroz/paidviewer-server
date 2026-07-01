"""add_streak_reset_on_skip_to_drops_config

Revision ID: 2dfdfeae5c56
Revises: 4fe4104541d9
Create Date: 2025-11-02 18:50:02.020588

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2dfdfeae5c56'
down_revision: Union[str, None] = '4fe4104541d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add streak_reset_on_skip column to drops_configs table
    with op.batch_alter_table('drops_configs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('streak_reset_on_skip', sa.Boolean(), nullable=True, server_default='true'))


def downgrade() -> None:
    # Remove streak_reset_on_skip column from drops_configs table
    with op.batch_alter_table('drops_configs', schema=None) as batch_op:
        batch_op.drop_column('streak_reset_on_skip')
