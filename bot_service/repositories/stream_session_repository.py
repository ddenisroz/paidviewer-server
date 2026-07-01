# bot_service/repositories/stream_session_repository.py
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

from repositories.base_repository import BaseRepository
from core.database import StreamSession


class StreamSessionRepository(BaseRepository[StreamSession]):
    """
    Repository for StreamSession entity.
    Handles active and past stream sessions.
    """
    def __init__(self, db: Session):
        super().__init__(StreamSession, db)

    def get_active_session(
        self,
        channel_name: str,
        platform: str,
        user_id: int = None,
        session_id: str = None
    ) -> Optional[StreamSession]:
        """Get currently active session for channel."""
        filters = [
            StreamSession.channel_name == channel_name,
            StreamSession.platform == platform,
            StreamSession.is_active.is_(True)
        ]
        
        if user_id:
            filters.append(StreamSession.user_id == user_id)
        elif session_id:
            filters.append(StreamSession.session_id == session_id)
        else:
            return None

        return self.db.query(StreamSession).filter(and_(*filters)).first()

    def get_old_active_sessions(
        self,
        channel_name: str,
        platform: str,
        user_id: int = None,
        session_id: str = None
    ) -> List[StreamSession]:
        """Get all active sessions to close them."""
        filters = [
            StreamSession.channel_name == channel_name,
            StreamSession.platform == platform,
            StreamSession.is_active.is_(True)
        ]

        if user_id:
            filters.append(StreamSession.user_id == user_id)
        elif session_id:
            filters.append(StreamSession.session_id == session_id)
        else:
            return []

        return self.db.query(StreamSession).filter(and_(*filters)).all()

    def get_last_session(
        self,
        channel_name: str,
        platform: str,
        user_id: int = None,
        session_id: str = None
    ) -> Optional[StreamSession]:
        """Get last session (active or ended)."""
        filters = [
            StreamSession.channel_name == channel_name,
            StreamSession.platform == platform
        ]

        if user_id:
            filters.append(StreamSession.user_id == user_id)
        elif session_id:
            filters.append(StreamSession.session_id == session_id)
        else:
            return None

        return (
            self.db.query(StreamSession)
            .filter(and_(*filters))
            .order_by(desc(StreamSession.started_at))
            .first()
        )

    def get_previous_session(
        self,
        channel_name: str,
        platform: str,
        user_id: int = None,
        session_id: str = None,
        exclude_session_id: int = None,
    ) -> Optional[StreamSession]:
        """Get the most recent session before the currently active one."""
        filters = [
            StreamSession.channel_name == channel_name,
            StreamSession.platform == platform,
        ]

        if exclude_session_id is not None:
            filters.append(StreamSession.id != exclude_session_id)

        if user_id:
            filters.append(StreamSession.user_id == user_id)
        elif session_id:
            filters.append(StreamSession.session_id == session_id)
        else:
            return None

        return (
            self.db.query(StreamSession)
            .filter(and_(*filters))
            .order_by(desc(StreamSession.started_at))
            .first()
        )

    def add_session(self, session: StreamSession) -> StreamSession:
        """Add new stream session."""
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def update_session(self, session: StreamSession) -> StreamSession:
        """Update existing session."""
        self.db.commit()
        self.db.refresh(session)
        return session
