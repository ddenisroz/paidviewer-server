"""add_tts_channel_points_mode

Revision ID: 02bdabb37f08
Revises: fcbce84c95fe
Create Date: 2025-10-28 19:31:39.626633

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '02bdabb37f08'
down_revision: Union[str, None] = 'fcbce84c95fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем режим работы TTS (all_messages или channel_points)
    op.add_column('tts_user_settings',
        sa.Column('tts_mode', sa.String(), nullable=False, server_default='all_messages')
    )

    # Добавляем JSON для хранения ID наград TTS для каждой платформы
    # Формат: {"twitch": "reward_id", "vk": "reward_id"}
    op.add_column('tts_user_settings',
        sa.Column('tts_reward_ids', sa.JSON(), nullable=False, server_default='{}')
    )


def downgrade() -> None:
    op.drop_column('tts_user_settings', 'tts_reward_ids')
    op.drop_column('tts_user_settings', 'tts_mode')
