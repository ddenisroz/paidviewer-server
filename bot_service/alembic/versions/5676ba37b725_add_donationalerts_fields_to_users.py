"""add_donationalerts_fields_to_users

Revision ID: 5676ba37b725
Revises: 75ba5c72b102
Create Date: 2025-09-27 18:14:24.703752

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5676ba37b725'
down_revision: Union[str, None] = '75ba5c72b102'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем поля для DonationAlerts интеграции
    op.add_column('users', sa.Column('donationalerts_access_token', sa.String(), nullable=True))
    op.add_column('users', sa.Column('donationalerts_refresh_token', sa.String(), nullable=True))
    op.add_column('users', sa.Column('donationalerts_token_expires', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('temp_oauth_state', sa.String(), nullable=True))


def downgrade() -> None:
    # Удаляем поля DonationAlerts при откате
    op.drop_column('users', 'temp_oauth_state')
    op.drop_column('users', 'donationalerts_token_expires')
    op.drop_column('users', 'donationalerts_refresh_token')
    op.drop_column('users', 'donationalerts_access_token')
