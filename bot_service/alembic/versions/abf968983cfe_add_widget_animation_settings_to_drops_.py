"""add_widget_animation_settings_to_drops_config

Revision ID: abf968983cfe
Revises: 2dfdfeae5c56
Create Date: 2025-11-02 19:57:25.545300

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'abf968983cfe'
down_revision: Union[str, None] = '2dfdfeae5c56'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add widget animation settings columns to drops_configs table
    with op.batch_alter_table('drops_configs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('widget_spinning_duration_ms', sa.Integer(), nullable=True, server_default='1500'))
        batch_op.add_column(sa.Column('widget_opening_duration_ms', sa.Integer(), nullable=True, server_default='1000'))
        batch_op.add_column(sa.Column('widget_result_duration_ms', sa.Integer(), nullable=True, server_default='5500'))
        batch_op.add_column(sa.Column('widget_closing_duration_ms', sa.Integer(), nullable=True, server_default='500'))


def downgrade() -> None:
    # Remove widget animation settings columns from drops_configs table
    with op.batch_alter_table('drops_configs', schema=None) as batch_op:
        batch_op.drop_column('widget_closing_duration_ms')
        batch_op.drop_column('widget_result_duration_ms')
        batch_op.drop_column('widget_opening_duration_ms')
        batch_op.drop_column('widget_spinning_duration_ms')
