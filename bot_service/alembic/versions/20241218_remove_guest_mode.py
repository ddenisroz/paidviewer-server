"""Remove guest mode

Revision ID: 20241218_remove_guest_mode
Revises: 20251215_auth_type
Create Date: 2024-12-18

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20241218_remove_guest_mode'
down_revision = '20251215_auth_type'
branch_labels = None
depends_on = None


def upgrade():
    """Remove guest mode tables and data"""
    
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()
    
    # 1. Drop vk_guest_verifications table
    if 'vk_guest_verifications' in existing_tables:
        op.execute("DROP TABLE vk_guest_verifications")
    
    # 2. Delete guest user sessions (user_id = -1) - only if table exists
    if 'user_sessions' in existing_tables:
        op.execute("DELETE FROM user_sessions WHERE user_id = -1")
    
    # 3. Delete guest user settings - only if tables exist
    if 'user_settings' in existing_tables:
        op.execute("DELETE FROM user_settings WHERE user_id = -1")
    if 'tts_user_settings' in existing_tables:
        op.execute("DELETE FROM tts_user_settings WHERE user_id = -1")
    if 'audio_settings' in existing_tables:
        op.execute("DELETE FROM audio_settings WHERE user_id = -1")
    if 'local_tts_endpoints' in existing_tables:
        op.execute("DELETE FROM local_tts_endpoints WHERE user_id = -1")
    
    # 4. Delete guest drops data - only if tables exist
    if 'drops_config' in existing_tables:
        op.execute("DELETE FROM drops_config WHERE user_id = -1")
    if 'drops_history' in existing_tables:
        op.execute("DELETE FROM drops_history WHERE user_id = -1")
    if 'user_streaks' in existing_tables:
        op.execute("DELETE FROM user_streaks WHERE user_id = -1")
    
    # 5. Delete guest YouTube queue - only if table exists
    if 'youtube_queue' in existing_tables:
        op.execute("DELETE FROM youtube_queue WHERE user_id = -1")


def downgrade():
    """Recreate vk_guest_verifications table"""
    
    op.create_table(
        'vk_guest_verifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('channel_name', sa.String(), nullable=False),
        sa.Column('verification_code', sa.String(), nullable=False),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_vk_guest_verifications_channel_name', 'vk_guest_verifications', ['channel_name'])
