"""Add filtered words table

Revision ID: add_filtered_words
Revises: psychology_analysis
Create Date: 2024-12-30 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision = 'add_filtered_words'
down_revision = 'psychology_analysis'
branch_labels = None
depends_on = None


def upgrade():
    # Create filtered_words table
    op.create_table('filtered_words',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('word', sa.String(), nullable=False),
        sa.Column('platform', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_filtered_words_id'), 'filtered_words', ['id'], unique=False)
    op.create_index(op.f('ix_filtered_words_created_at'), 'filtered_words', ['created_at'], unique=False)
    op.create_index('idx_user_word', 'filtered_words', ['user_id', 'word'], unique=False)
    op.create_index('idx_platform', 'filtered_words', ['platform'], unique=False)
    op.create_index('idx_active', 'filtered_words', ['is_active'], unique=False)


def downgrade():
    op.drop_index('idx_active', table_name='filtered_words')
    op.drop_index('idx_platform', table_name='filtered_words')
    op.drop_index('idx_user_word', table_name='filtered_words')
    op.drop_index(op.f('ix_filtered_words_created_at'), table_name='filtered_words')
    op.drop_index(op.f('ix_filtered_words_id'), table_name='filtered_words')
    op.drop_table('filtered_words')
