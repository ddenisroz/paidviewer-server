"""add role fields to users

Revision ID: 20251114_add_role_fields
Revises: 251db88ff969
Create Date: 2025-11-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251114_add_role_fields'
down_revision = '251db88ff969'  # Latest migration
branch_labels = None
depends_on = None


def upgrade():
    """Add role fields to users table"""
    # Add application role field
    op.add_column('users', sa.Column('role', sa.String(), nullable=False, server_default='user'))
    op.create_index(op.f('ix_users_role'), 'users', ['role'], unique=False)

    # Add Twitch platform role fields
    op.add_column('users', sa.Column('twitch_is_broadcaster', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('twitch_is_moderator', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('twitch_is_vip', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('twitch_is_subscriber', sa.Boolean(), nullable=False, server_default='false'))

    # Add VK platform role fields
    op.add_column('users', sa.Column('vk_is_owner', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('vk_is_moderator', sa.Boolean(), nullable=False, server_default='false'))

    # Migrate existing is_admin users to admin role
    op.execute("UPDATE users SET role = 'admin' WHERE is_admin = true")


def downgrade():
    """Remove role fields from users table"""
    # Remove VK platform role fields
    op.drop_column('users', 'vk_is_moderator')
    op.drop_column('users', 'vk_is_owner')

    # Remove Twitch platform role fields
    op.drop_column('users', 'twitch_is_subscriber')
    op.drop_column('users', 'twitch_is_vip')
    op.drop_column('users', 'twitch_is_moderator')
    op.drop_column('users', 'twitch_is_broadcaster')

    # Remove application role field
    op.drop_index(op.f('ix_users_role'), table_name='users')
    op.drop_column('users', 'role')
