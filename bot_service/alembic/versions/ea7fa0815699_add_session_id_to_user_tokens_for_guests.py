"""add_session_id_to_user_tokens_for_guests

Revision ID: ea7fa0815699
Revises: cc453a20591e
Create Date: 2025-11-02 17:05:53.937618

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ea7fa0815699'
down_revision: Union[str, None] = 'cc453a20591e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add session_id support to UserToken for guest DonationAlerts"""

    # UserToken: add session_id, make user_id nullable, add constraint
    with op.batch_alter_table('user_tokens', schema=None) as batch_op:
        # Make user_id nullable
        batch_op.alter_column('user_id',
                              existing_type=sa.INTEGER(),
                              nullable=True)
        # Add session_id
        batch_op.add_column(sa.Column('session_id', sa.String(), nullable=True))
        batch_op.create_index('ix_user_tokens_session_id', ['session_id'])

        # Add constraint
        batch_op.create_check_constraint(
            'check_user_or_session_token',
            '(user_id IS NOT NULL AND session_id IS NULL) OR (user_id IS NULL AND session_id IS NOT NULL)'
        )


def downgrade() -> None:
    """Remove session_id support from UserToken"""

    with op.batch_alter_table('user_tokens', schema=None) as batch_op:
        batch_op.drop_constraint('check_user_or_session_token', type_='check')
        batch_op.drop_index('ix_user_tokens_session_id')
        batch_op.drop_column('session_id')
        batch_op.alter_column('user_id',
                              existing_type=sa.INTEGER(),
                              nullable=False)
