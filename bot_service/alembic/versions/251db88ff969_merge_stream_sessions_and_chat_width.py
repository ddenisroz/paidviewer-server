"""merge_stream_sessions_and_chat_width

Revision ID: 251db88ff969
Revises: 20251109_stream_sessions, 63c95740b7f7
Create Date: 2025-11-09 17:40:56.245288

"""
from typing import Sequence, Union



# revision identifiers, used by Alembic.
revision: str = '251db88ff969'
down_revision: Union[str, None] = ('20251109_stream_sessions', '63c95740b7f7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
