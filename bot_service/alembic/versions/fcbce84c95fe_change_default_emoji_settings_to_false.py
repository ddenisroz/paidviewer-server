"""change_default_emoji_settings_to_false

Revision ID: fcbce84c95fe
Revises: 3c4d5e6f7g8h
Create Date: 2025-10-27 10:54:43.493230

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fcbce84c95fe'
down_revision: Union[str, None] = '3c4d5e6f7g8h'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Изменяем дефолтные значения для enable_7tv и enable_twitch на False
    # Это повлияет только на НОВЫХ пользователей, существующие настройки не изменятся
    with op.batch_alter_table('tts_user_settings', schema=None) as batch_op:
        batch_op.alter_column('enable_7tv',
                              existing_type=sa.Boolean(),
                              server_default='0',
                              existing_nullable=False)
        batch_op.alter_column('enable_twitch',
                              existing_type=sa.Boolean(),
                              server_default='0',
                              existing_nullable=False)


def downgrade() -> None:
    # Возвращаем дефолтные значения обратно на True
    with op.batch_alter_table('tts_user_settings', schema=None) as batch_op:
        batch_op.alter_column('enable_7tv',
                              existing_type=sa.Boolean(),
                              server_default='1',
                              existing_nullable=False)
        batch_op.alter_column('enable_twitch',
                              existing_type=sa.Boolean(),
                              server_default='1',
                              existing_nullable=False)
