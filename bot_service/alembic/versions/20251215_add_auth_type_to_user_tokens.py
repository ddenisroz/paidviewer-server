"""add auth_type to user_tokens

Revision ID: 20251215_auth_type
Revises: 
Create Date: 2024-12-15

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251215_auth_type'
down_revision = 'dfa2f970ed79'
branch_labels = None
depends_on = None


def upgrade():
    """Add auth_type column to user_tokens table.
    
    auth_type: 'full' - full authorization (all scopes), 'basic' - simplified (minimal scopes)
    """
    # Check if column already exists (for idempotency)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('user_tokens')]

    if 'auth_type' not in columns:
        op.add_column(
            'user_tokens',
            sa.Column('auth_type', sa.String(), nullable=False, server_default='full')
        )
        # Add index for better query performance
        op.create_index('ix_user_tokens_auth_type', 'user_tokens', ['auth_type'])


def downgrade():
    """Remove auth_type column from user_tokens table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('user_tokens')]

    if 'auth_type' in columns:
        op.drop_index('ix_user_tokens_auth_type', table_name='user_tokens')
        op.drop_column('user_tokens', 'auth_type')
