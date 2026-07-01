"""add_widget_token_to_drops_config

Revision ID: add_widget_token
Revises: 
Create Date: 2025-11-03

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_widget_token'
down_revision = '4cf879f958cd'  # add_performance_indexes
branch_labels = None
depends_on = None


def upgrade():
    # Добавляем столбец widget_token в таблицу drops_configs
    op.add_column('drops_configs', sa.Column('widget_token', sa.String(), nullable=True))
    op.create_index('ix_drops_configs_widget_token', 'drops_configs', ['widget_token'], unique=True)


def downgrade():
    # Удаляем столбец widget_token
    op.drop_index('ix_drops_configs_widget_token', table_name='drops_configs')
    op.drop_column('drops_configs', 'widget_token')

