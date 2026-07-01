"""Add 7TV emotes, links, and image loading settings to ChatBoxSettings

Revision ID: 20251105_7tv_links_images
Revises: 20251101_add_session_id_to_guest_tables
Create Date: 2025-11-05 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20251105_7tv_links_images'
down_revision: Union[str, None] = 'ea7fa0815699'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add 7TV emotes, links, and image loading settings to ChatBoxSettings"""
    # Добавляем новые колонки для поддержки 7TV эмодзи, ссылок и загрузки картинок
    op.add_column('chatbox_settings', sa.Column('show_7tv_emotes', sa.Boolean(), nullable=True, server_default='true'))
    op.add_column('chatbox_settings', sa.Column('show_links', sa.Boolean(), nullable=True, server_default='true'))
    op.add_column('chatbox_settings', sa.Column('auto_load_images', sa.Boolean(), nullable=True, server_default='true'))


def downgrade() -> None:
    """Remove 7TV emotes, links, and image loading settings from ChatBoxSettings"""
    # Удаляем колонки при откате миграции
    op.drop_column('chatbox_settings', 'auto_load_images')
    op.drop_column('chatbox_settings', 'show_links')
    op.drop_column('chatbox_settings', 'show_7tv_emotes')

