"""add_session_id_to_drops_tables_for_guests

Revision ID: 4fe4104541d9
Revises: ea7fa0815699
Create Date: 2025-11-02 17:17:11.613892

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4fe4104541d9'
down_revision: Union[str, None] = 'ea7fa0815699'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add session_id support to Drops tables for guests"""

    # 1. DropsConfig: add session_id, make user_id nullable, add constraint
    with op.batch_alter_table('drops_configs', schema=None) as batch_op:
        batch_op.alter_column('user_id',
                              existing_type=sa.INTEGER(),
                              nullable=True)
        batch_op.add_column(sa.Column('session_id', sa.String(), nullable=True))
        batch_op.create_index('ix_drops_configs_session_id', ['session_id'])
        batch_op.create_check_constraint(
            'check_user_or_session_drops_config',
            '(user_id IS NOT NULL AND session_id IS NULL) OR (user_id IS NULL AND session_id IS NOT NULL)'
        )

    # 2. DropsReward: add session_id, make user_id nullable, add constraint
    with op.batch_alter_table('drops_rewards', schema=None) as batch_op:
        batch_op.alter_column('user_id',
                              existing_type=sa.INTEGER(),
                              nullable=True)
        batch_op.add_column(sa.Column('session_id', sa.String(), nullable=True))
        batch_op.create_index('ix_drops_rewards_session_id', ['session_id'])
        batch_op.create_check_constraint(
            'check_user_or_session_drops_reward',
            '(user_id IS NOT NULL AND session_id IS NULL) OR (user_id IS NULL AND session_id IS NOT NULL)'
        )

    # 3. UserStreak: add session_id, make user_id nullable, add constraint, update unique constraint
    with op.batch_alter_table('user_streaks', schema=None) as batch_op:
        # Drop old unique constraint first
        batch_op.drop_constraint('uq_user_streak', type_='unique')
        batch_op.alter_column('user_id',
                              existing_type=sa.INTEGER(),
                              nullable=True)
        batch_op.add_column(sa.Column('session_id', sa.String(), nullable=True))
        batch_op.create_index('ix_user_streaks_session_id', ['session_id'])
        # Create new unique constraint with session_id support
        batch_op.create_unique_constraint(
            'uq_user_streak',
            ['user_id', 'viewer_id', 'platform']
        )
        batch_op.create_unique_constraint(
            'uq_session_streak',
            ['session_id', 'viewer_id', 'platform']
        )
        batch_op.create_check_constraint(
            'check_user_or_session_user_streak',
            '(user_id IS NOT NULL AND session_id IS NULL) OR (user_id IS NULL AND session_id IS NOT NULL)'
        )

    # 4. DropsHistory: add session_id, make user_id nullable, add constraint
    with op.batch_alter_table('drops_history', schema=None) as batch_op:
        batch_op.alter_column('user_id',
                              existing_type=sa.INTEGER(),
                              nullable=True)
        batch_op.add_column(sa.Column('session_id', sa.String(), nullable=True))
        batch_op.create_index('ix_drops_history_session_id', ['session_id'])
        batch_op.create_check_constraint(
            'check_user_or_session_drops_history',
            '(user_id IS NOT NULL AND session_id IS NULL) OR (user_id IS NULL AND session_id IS NOT NULL)'
        )

    # 5. MythicalDropsSession: add session_id, make user_id nullable, add constraint
    with op.batch_alter_table('mythical_drops_sessions', schema=None) as batch_op:
        batch_op.alter_column('user_id',
                              existing_type=sa.INTEGER(),
                              nullable=True)
        batch_op.add_column(sa.Column('session_id', sa.String(), nullable=True))
        batch_op.create_index('ix_mythical_drops_sessions_session_id', ['session_id'])
        batch_op.create_check_constraint(
            'check_user_or_session_mythical_drops',
            '(user_id IS NOT NULL AND session_id IS NULL) OR (user_id IS NULL AND session_id IS NOT NULL)'
        )


def downgrade() -> None:
    """Remove session_id support from Drops tables"""

    # MythicalDropsSession
    with op.batch_alter_table('mythical_drops_sessions', schema=None) as batch_op:
        batch_op.drop_constraint('check_user_or_session_mythical_drops', type_='check')
        batch_op.drop_index('ix_mythical_drops_sessions_session_id')
        batch_op.drop_column('session_id')
        batch_op.alter_column('user_id',
                              existing_type=sa.INTEGER(),
                              nullable=False)

    # DropsHistory
    with op.batch_alter_table('drops_history', schema=None) as batch_op:
        batch_op.drop_constraint('check_user_or_session_drops_history', type_='check')
        batch_op.drop_index('ix_drops_history_session_id')
        batch_op.drop_column('session_id')
        batch_op.alter_column('user_id',
                              existing_type=sa.INTEGER(),
                              nullable=False)

    # UserStreak
    with op.batch_alter_table('user_streaks', schema=None) as batch_op:
        batch_op.drop_constraint('uq_session_streak', type_='unique')
        batch_op.drop_constraint('uq_user_streak', type_='unique')
        batch_op.drop_constraint('check_user_or_session_user_streak', type_='check')
        batch_op.drop_index('ix_user_streaks_session_id')
        batch_op.drop_column('session_id')
        batch_op.alter_column('user_id',
                              existing_type=sa.INTEGER(),
                              nullable=False)
        batch_op.create_unique_constraint(
            'uq_user_streak',
            ['user_id', 'viewer_id', 'platform']
        )

    # DropsReward
    with op.batch_alter_table('drops_rewards', schema=None) as batch_op:
        batch_op.drop_constraint('check_user_or_session_drops_reward', type_='check')
        batch_op.drop_index('ix_drops_rewards_session_id')
        batch_op.drop_column('session_id')
        batch_op.alter_column('user_id',
                              existing_type=sa.INTEGER(),
                              nullable=False)

    # DropsConfig
    with op.batch_alter_table('drops_configs', schema=None) as batch_op:
        batch_op.drop_constraint('check_user_or_session_drops_config', type_='check')
        batch_op.drop_index('ix_drops_configs_session_id')
        batch_op.drop_column('session_id')
        batch_op.alter_column('user_id',
                              existing_type=sa.INTEGER(),
                              nullable=False)
