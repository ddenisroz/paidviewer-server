"""add session_id to guest tables

Revision ID: 20251101_add_session_id
Revises: 5723f1288b27
Create Date: 2025-11-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251101_add_session_id'
down_revision = '5723f1288b27'
branch_labels = None
depends_on = None


def upgrade():
    """Add session_id support to FilteredWord, TTSBlockedUser, and YouTubeQueue"""

    # 1. FilteredWord: add session_id, make user_id nullable, add constraint
    with op.batch_alter_table('filtered_words', schema=None) as batch_op:
        # Make user_id nullable
        batch_op.alter_column('user_id',
                              existing_type=sa.INTEGER(),
                              nullable=True)
        # Add session_id
        batch_op.add_column(sa.Column('session_id', sa.String(), nullable=True))
        batch_op.create_index('ix_filtered_words_session_id', ['session_id'])

        # Add constraints
        batch_op.create_index('idx_session_word', ['session_id', 'word'])
        batch_op.create_unique_constraint(
            'uq_session_word_platform',
            ['session_id', 'word', 'platform']
        )
        batch_op.create_check_constraint(
            'check_user_or_session_filtered_word',
            '(user_id IS NOT NULL AND session_id IS NULL) OR (user_id IS NULL AND session_id IS NOT NULL)'
        )

    # 2. TTSBlockedUser: add session_id, make user_id nullable, add constraint
    with op.batch_alter_table('tts_blocked_users', schema=None) as batch_op:
        # Make user_id nullable
        batch_op.alter_column('user_id',
                              existing_type=sa.INTEGER(),
                              nullable=True)
        # Add session_id
        batch_op.add_column(sa.Column('session_id', sa.String(), nullable=True))
        batch_op.create_index('ix_tts_blocked_users_session_id', ['session_id'])

        # Add constraint
        batch_op.create_check_constraint(
            'check_user_or_session_tts_blocked_user',
            '(user_id IS NOT NULL AND session_id IS NULL) OR (user_id IS NULL AND session_id IS NOT NULL)'
        )

    # 3. YouTubeQueue: add session_id, make user_id nullable, add constraint
    with op.batch_alter_table('youtube_queue', schema=None) as batch_op:
        # Make user_id nullable
        batch_op.alter_column('user_id',
                              existing_type=sa.INTEGER(),
                              nullable=True)
        # Add session_id
        batch_op.add_column(sa.Column('session_id', sa.String(), nullable=True))
        batch_op.create_index('ix_youtube_queue_session_id', ['session_id'])

        # Add constraint
        batch_op.create_check_constraint(
            'check_user_or_session_youtube_queue',
            '(user_id IS NOT NULL AND session_id IS NULL) OR (user_id IS NULL AND session_id IS NOT NULL)'
        )


def downgrade():
    """Remove session_id support from guest tables"""

    # YouTubeQueue
    with op.batch_alter_table('youtube_queue', schema=None) as batch_op:
        batch_op.drop_constraint('check_user_or_session_youtube_queue', type_='check')
        batch_op.drop_index('ix_youtube_queue_session_id')
        batch_op.drop_column('session_id')
        batch_op.alter_column('user_id',
                              existing_type=sa.INTEGER(),
                              nullable=False)

    # TTSBlockedUser
    with op.batch_alter_table('tts_blocked_users', schema=None) as batch_op:
        batch_op.drop_constraint('check_user_or_session_tts_blocked_user', type_='check')
        batch_op.drop_index('ix_tts_blocked_users_session_id')
        batch_op.drop_column('session_id')
        batch_op.alter_column('user_id',
                              existing_type=sa.INTEGER(),
                              nullable=False)

    # FilteredWord
    with op.batch_alter_table('filtered_words', schema=None) as batch_op:
        batch_op.drop_constraint('check_user_or_session_filtered_word', type_='check')
        batch_op.drop_constraint('uq_session_word_platform', type_='unique')
        batch_op.drop_index('idx_session_word')
        batch_op.drop_index('ix_filtered_words_session_id')
        batch_op.drop_column('session_id')
        batch_op.alter_column('user_id',
                              existing_type=sa.INTEGER(),
                              nullable=False)

