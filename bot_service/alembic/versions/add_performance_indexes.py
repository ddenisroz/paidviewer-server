"""Add performance indexes for User model

Revision ID: add_performance_indexes
Revises: 
Create Date: 2025-11-14

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = 'add_performance_indexes'
down_revision = '20251114_add_role_fields'  # Must run after role fields are added
branch_labels = None
depends_on = None


def upgrade():
    """Add performance indexes to User model"""
    
    # Add case-insensitive index for twitch_username lookups
    # PostgreSQL supports functional indexes
    op.execute(text(
        'CREATE INDEX IF NOT EXISTS idx_users_twitch_username_lower '
        'ON users (LOWER(twitch_username))'
    ))
    
    # Add case-insensitive index for vk_username lookups
    op.execute(text(
        'CREATE INDEX IF NOT EXISTS idx_users_vk_username_lower '
        'ON users (LOWER(vk_username))'
    ))
    
    # Add index for vk_channel_name lookups
    op.execute(text(
        'CREATE INDEX IF NOT EXISTS idx_users_vk_channel_name_lower '
        'ON users (LOWER(vk_channel_name))'
    ))
    
    # Add composite index for active users by role
    op.execute(text(
        'CREATE INDEX IF NOT EXISTS idx_users_active_role '
        'ON users (is_active, role) '
        'WHERE is_active = true'
    ))
    
    # Add index for blocked users
    op.execute(text(
        'CREATE INDEX IF NOT EXISTS idx_users_blocked '
        'ON users (is_blocked, blocked_at) '
        'WHERE is_blocked = true'
    ))
    
    # Add index for OBS token lookups
    op.execute(text(
        'CREATE INDEX IF NOT EXISTS idx_users_obs_token '
        'ON users (obs_token) '
        'WHERE obs_token IS NOT NULL'
    ))


def downgrade():
    """Remove performance indexes"""
    
    op.execute(text('DROP INDEX IF EXISTS idx_users_twitch_username_lower'))
    op.execute(text('DROP INDEX IF EXISTS idx_users_vk_username_lower'))
    op.execute(text('DROP INDEX IF EXISTS idx_users_vk_channel_name_lower'))
    op.execute(text('DROP INDEX IF EXISTS idx_users_active_role'))
    op.execute(text('DROP INDEX IF EXISTS idx_users_blocked'))
    op.execute(text('DROP INDEX IF EXISTS idx_users_obs_token'))
