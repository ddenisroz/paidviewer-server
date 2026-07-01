"""add_session_id_to_local_tts_endpoints

Revision ID: 0c8f9a3b4d2e
Revises: 7398efb7a962
Create Date: 2025-10-27 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0c8f9a3b4d2e'
down_revision = '7f15d1d3ff0f'
branch_labels = None
depends_on = None


def upgrade():
    # Делаем user_id nullable и добавляем session_id
    with op.batch_alter_table('local_tts_endpoints', schema=None) as batch_op:
        batch_op.alter_column('user_id',
                              existing_type=sa.INTEGER(),
                              nullable=True)
        batch_op.add_column(sa.Column('session_id', sa.String(), nullable=True))
        batch_op.create_index('ix_local_tts_endpoints_session_id', ['session_id'])

        # Добавляем constraint: должен быть заполнен либо user_id, либо session_id
        batch_op.create_check_constraint(
            'check_user_or_session_local_tts',
            '(user_id IS NOT NULL AND session_id IS NULL) OR (user_id IS NULL AND session_id IS NOT NULL)'
        )


def downgrade():
    with op.batch_alter_table('local_tts_endpoints', schema=None) as batch_op:
        batch_op.drop_constraint('check_user_or_session_local_tts', type_='check')
        batch_op.drop_index('ix_local_tts_endpoints_session_id')
        batch_op.drop_column('session_id')
        batch_op.alter_column('user_id',
                              existing_type=sa.INTEGER(),
                              nullable=False)

