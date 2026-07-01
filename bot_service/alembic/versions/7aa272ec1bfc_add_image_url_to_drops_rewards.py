"""add_image_url_to_drops_rewards

Revision ID: 7aa272ec1bfc
Revises: abf968983cfe
Create Date: 2025-11-02 21:32:31.113881

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7aa272ec1bfc'
down_revision: Union[str, None] = 'abf968983cfe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add image_url column to drops_rewards table
    with op.batch_alter_table('drops_rewards', schema=None) as batch_op:
        batch_op.add_column(sa.Column('image_url', sa.String(length=1000), nullable=True))


def downgrade() -> None:
    # Remove image_url column from drops_rewards table
    with op.batch_alter_table('drops_rewards', schema=None) as batch_op:
        batch_op.drop_column('image_url')
