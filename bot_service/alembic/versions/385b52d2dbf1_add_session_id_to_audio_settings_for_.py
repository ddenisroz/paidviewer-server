"""add_session_id_to_audio_settings_for_guests

Revision ID: 385b52d2dbf1
Revises: add_widget_token
Create Date: 2025-11-05 16:31:15.060662

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '385b52d2dbf1'
down_revision: Union[str, None] = 'add_widget_token'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add session_id support to AudioSettings for guest users (PostgreSQL only)"""

    # Remove old unique constraint on user_id if it exists
    try:
        op.execute(sa.text('ALTER TABLE audio_settings DROP CONSTRAINT IF EXISTS audio_settings_user_id_key'))
    except Exception:
        # Try alternative constraint name
        try:
            op.execute(sa.text('ALTER TABLE audio_settings DROP CONSTRAINT IF EXISTS uq_audio_settings_user_id'))
        except Exception:
            pass

    # AudioSettings: add session_id, make user_id nullable, add constraint
    with op.batch_alter_table('audio_settings', schema=None) as batch_op:
        # Make user_id nullable
        batch_op.alter_column('user_id',
                              existing_type=sa.INTEGER(),
                              nullable=True)

        # Add session_id column
        batch_op.add_column(sa.Column('session_id', sa.String(), nullable=True))

        # Create index for session_id
        batch_op.create_index('ix_audio_settings_session_id', ['session_id'])

        # Add check constraint: either user_id or session_id must be set, but not both
        batch_op.create_check_constraint(
            'check_user_or_session_audio_settings',
            '(user_id IS NOT NULL AND session_id IS NULL) OR (user_id IS NULL AND session_id IS NOT NULL)'
        )

    # Create partial unique indexes AFTER the column is added
    # (outside of batch_alter_table context)
    # Partial unique index for user_id (only when user_id IS NOT NULL)
    op.execute(sa.text(
        'CREATE UNIQUE INDEX IF NOT EXISTS uq_audio_settings_user_id '
        'ON audio_settings (user_id) '
        'WHERE user_id IS NOT NULL'
    ))

    # Partial unique index for session_id (only when session_id IS NOT NULL)
    op.execute(sa.text(
        'CREATE UNIQUE INDEX IF NOT EXISTS uq_audio_settings_session_id '
        'ON audio_settings (session_id) '
        'WHERE session_id IS NOT NULL'
    ))


def downgrade() -> None:
    """Remove session_id support from AudioSettings (PostgreSQL only)"""

    # Drop PostgreSQL partial unique indexes
    try:
        op.execute(sa.text('DROP INDEX IF EXISTS uq_audio_settings_user_id'))
    except Exception:
        pass
    try:
        op.execute(sa.text('DROP INDEX IF EXISTS uq_audio_settings_session_id'))
    except Exception:
        pass

    with op.batch_alter_table('audio_settings', schema=None) as batch_op:
        # Drop check constraint
        batch_op.drop_constraint('check_user_or_session_audio_settings', type_='check')

        # Drop index
        batch_op.drop_index('ix_audio_settings_session_id')

        # Drop session_id column
        batch_op.drop_column('session_id')

        # Make user_id NOT NULL again
        # Note: This will fail if there are NULL values in the database
        # In that case, you need to manually clean up NULL values first
        batch_op.alter_column('user_id',
                              existing_type=sa.INTEGER(),
                              nullable=False)

    # Restore unique constraint on user_id
    op.execute(sa.text(
        'ALTER TABLE audio_settings '
        'ADD CONSTRAINT audio_settings_user_id_key UNIQUE (user_id)'
    ))
