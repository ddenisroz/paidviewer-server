"""add fundamental constraints and indexes

Revision ID: 20251218_fundamental
Revises: 122026a49dfb
Create Date: 2025-12-18 12:00:00.000000

"""
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision = '20251218_fundamental'
down_revision = '122026a49dfb'
branch_labels = None
depends_on = None


def constraint_exists(conn, table_name, constraint_name):
    """Check if constraint exists"""
    inspector = Inspector.from_engine(conn)
    constraints = []
    
    try:
        for uc in inspector.get_unique_constraints(table_name):
            if uc.get('name'):
                constraints.append(uc['name'])
    except Exception:
        pass
    
    try:
        for fk in inspector.get_foreign_keys(table_name):
            if fk.get('name'):
                constraints.append(fk['name'])
    except Exception:
        pass
    
    try:
        for cc in inspector.get_check_constraints(table_name):
            if cc.get('name'):
                constraints.append(cc['name'])
    except Exception:
        pass
    
    return constraint_name in constraints


def index_exists(conn, table_name, index_name):
    """Check if index exists"""
    try:
        inspector = Inspector.from_engine(conn)
        indexes = inspector.get_indexes(table_name)
        return any(idx.get('name') == index_name for idx in indexes)
    except Exception:
        return False


def table_exists(conn, table_name):
    """Check if table exists"""
    try:
        inspector = Inspector.from_engine(conn)
        return table_name in inspector.get_table_names()
    except Exception:
        return False


def upgrade():
    conn = op.get_bind()
    
    print("=" * 60)
    print("Adding fundamental constraints and indexes...")
    print("=" * 60)
    
    # USER_TOKENS
    if table_exists(conn, 'user_tokens'):
        print("\n[USER_TOKENS]")
        
        if not constraint_exists(conn, 'user_tokens', 'uq_user_tokens_user_platform'):
            try:
                op.create_unique_constraint(
                    'uq_user_tokens_user_platform',
                    'user_tokens',
                    ['user_id', 'platform']
                )
                print("   Added UNIQUE constraint: user_id + platform")
            except Exception as e:
                print(f"  ⚠️  Skipped: {e}")
        
        if not constraint_exists(conn, 'user_tokens', 'ck_user_tokens_platform'):
            try:
                op.create_check_constraint(
                    'ck_user_tokens_platform',
                    'user_tokens',
                    "platform IN ('twitch', 'vk', 'donationalerts')"
                )
                print("   Added CHECK constraint: platform")
            except Exception as e:
                print(f"  ⚠️  Skipped: {e}")
        
        if not index_exists(conn, 'user_tokens', 'idx_user_tokens_platform_user'):
            try:
                op.create_index(
                    'idx_user_tokens_platform_user',
                    'user_tokens',
                    ['platform', 'platform_user_id']
                )
                print("   Added INDEX: platform + platform_user_id")
            except Exception as e:
                print(f"  ⚠️  Skipped: {e}")
    
    # CHAT_MESSAGES
    if table_exists(conn, 'chat_messages'):
        print("\n[CHAT_MESSAGES]")
        
        if not constraint_exists(conn, 'chat_messages', 'ck_chat_messages_platform'):
            try:
                op.create_check_constraint(
                    'ck_chat_messages_platform',
                    'chat_messages',
                    "platform IN ('twitch', 'vk')"
                )
                print("   Added CHECK constraint: platform")
            except Exception as e:
                print(f"  ⚠️  Skipped: {e}")
        
        if not index_exists(conn, 'chat_messages', 'idx_chat_messages_user_timestamp'):
            try:
                op.create_index(
                    'idx_chat_messages_user_timestamp',
                    'chat_messages',
                    ['user_id', 'timestamp']
                )
                print("   Added INDEX: user_id + timestamp")
            except Exception as e:
                print(f"  ⚠️  Skipped: {e}")
    
    # YOUTUBE_QUEUE
    if table_exists(conn, 'youtube_queue'):
        print("\n[YOUTUBE_QUEUE]")
        
        if not constraint_exists(conn, 'youtube_queue', 'ck_youtube_queue_status'):
            try:
                op.create_check_constraint(
                    'ck_youtube_queue_status',
                    'youtube_queue',
                    "status IN ('pending', 'playing', 'played', 'skipped')"
                )
                print("   Added CHECK constraint: status")
            except Exception as e:
                print(f"  ⚠️  Skipped: {e}")
        
        if not index_exists(conn, 'youtube_queue', 'idx_youtube_queue_user_status'):
            try:
                op.create_index(
                    'idx_youtube_queue_user_status',
                    'youtube_queue',
                    ['user_id', 'status']
                )
                print("   Added INDEX: user_id + status")
            except Exception as e:
                print(f"  ⚠️  Skipped: {e}")
    
    # USER_STREAKS
    if table_exists(conn, 'user_streaks'):
        print("\n[USER_STREAKS]")
        
        if not constraint_exists(conn, 'user_streaks', 'uq_user_streaks_user_platform'):
            try:
                op.create_unique_constraint(
                    'uq_user_streaks_user_platform',
                    'user_streaks',
                    ['user_id', 'platform']
                )
                print("   Added UNIQUE constraint: user_id + platform")
            except Exception as e:
                print(f"  ⚠️  Skipped: {e}")
        
        if not constraint_exists(conn, 'user_streaks', 'ck_user_streaks_platform'):
            try:
                op.create_check_constraint(
                    'ck_user_streaks_platform',
                    'user_streaks',
                    "platform IN ('twitch', 'vk')"
                )
                print("   Added CHECK constraint: platform")
            except Exception as e:
                print(f"  ⚠️  Skipped: {e}")
    
    print("\n" + "=" * 60)
    print(" Fundamental constraints and indexes added")
    print("=" * 60)


def downgrade():
    conn = op.get_bind()
    
    if table_exists(conn, 'user_streaks'):
        if constraint_exists(conn, 'user_streaks', 'ck_user_streaks_platform'):
            op.drop_constraint('ck_user_streaks_platform', 'user_streaks')
        if constraint_exists(conn, 'user_streaks', 'uq_user_streaks_user_platform'):
            op.drop_constraint('uq_user_streaks_user_platform', 'user_streaks')
    
    if table_exists(conn, 'youtube_queue'):
        if index_exists(conn, 'youtube_queue', 'idx_youtube_queue_user_status'):
            op.drop_index('idx_youtube_queue_user_status', 'youtube_queue')
        if constraint_exists(conn, 'youtube_queue', 'ck_youtube_queue_status'):
            op.drop_constraint('ck_youtube_queue_status', 'youtube_queue')
    
    if table_exists(conn, 'chat_messages'):
        if index_exists(conn, 'chat_messages', 'idx_chat_messages_user_timestamp'):
            op.drop_index('idx_chat_messages_user_timestamp', 'chat_messages')
        if constraint_exists(conn, 'chat_messages', 'ck_chat_messages_platform'):
            op.drop_constraint('ck_chat_messages_platform', 'chat_messages')
    
    if table_exists(conn, 'user_tokens'):
        if index_exists(conn, 'user_tokens', 'idx_user_tokens_platform_user'):
            op.drop_index('idx_user_tokens_platform_user', 'user_tokens')
        if constraint_exists(conn, 'user_tokens', 'ck_user_tokens_platform'):
            op.drop_constraint('ck_user_tokens_platform', 'user_tokens')
        if constraint_exists(conn, 'user_tokens', 'uq_user_tokens_user_platform'):
            op.drop_constraint('uq_user_tokens_user_platform', 'user_tokens')
    
    print(" Constraints and indexes removed")
