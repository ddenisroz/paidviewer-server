"""Add psychology analysis table

Revision ID: psychology_analysis
Revises: add_command_tags
Create Date: 2024-12-30 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision = 'psychology_analysis'
down_revision = 'add_command_tags'
branch_labels = None
depends_on = None


def upgrade():
    # Create psychology_analysis table
    op.create_table('psychology_analysis',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('target_user_id', sa.Integer(), nullable=False),
        sa.Column('target_username', sa.String(), nullable=False),
        sa.Column('platform', sa.String(), nullable=False),
        sa.Column('analyzed_by_user_id', sa.Integer(), nullable=False),
        sa.Column('analyzed_by_username', sa.String(), nullable=False),
        sa.Column('analysis_text', sa.Text(), nullable=False),
        sa.Column('messages_count', sa.Integer(), nullable=False),
        sa.Column('analysis_date', sa.DateTime(), nullable=True),
        sa.Column('ai_model_used', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['analyzed_by_user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['target_user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_psychology_analysis_id'), 'psychology_analysis', ['id'], unique=False)
    op.create_index(op.f('ix_psychology_analysis_analysis_date'), 'psychology_analysis', ['analysis_date'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_psychology_analysis_analysis_date'), table_name='psychology_analysis')
    op.drop_index(op.f('ix_psychology_analysis_id'), table_name='psychology_analysis')
    op.drop_table('psychology_analysis')
