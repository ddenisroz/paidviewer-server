"""Service for tracking stream sessions and viewer attendance."""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from core.database import StreamSession
from core.datetime_utils import utcnow_naive
from repositories.drops_history_repository import DropsHistoryRepository
from repositories.stream_session_repository import StreamSessionRepository

logger = logging.getLogger(__name__)


class StreamSessionService:
    """Business logic for stream session lifecycle management."""

    def __init__(self, db: Session):
        self.db = db
        self.session_repo = StreamSessionRepository(db)
        self.streak_repo = DropsHistoryRepository(db)

    def get_or_create_active_user_session(
        self,
        user_id: int,
        channel_name: str = None,
        platform: str = "twitch",
        title: str = None,
    ) -> Optional[StreamSession]:
        """Active user-only wrapper for stream session lifecycle."""
        return self.get_or_create_active_session(
            user_id=user_id,
            session_id=None,
            channel_name=channel_name,
            platform=platform,
            title=title,
        )

    def get_last_user_session(
        self,
        user_id: int,
        channel_name: str = None,
        platform: str = "twitch",
    ) -> Optional[StreamSession]:
        """Active user-only wrapper for previous stream session lookup."""
        return self.get_last_session(
            user_id=user_id,
            session_id=None,
            channel_name=channel_name,
            platform=platform,
        )

    def get_active_user_session(
        self,
        user_id: int,
        channel_name: str = None,
        platform: str = "twitch",
    ) -> Optional[StreamSession]:
        """Active user-only wrapper for current stream session lookup."""
        return self.get_active_session(
            user_id=user_id,
            session_id=None,
            channel_name=channel_name,
            platform=platform,
        )

    def get_previous_user_session(
        self,
        user_id: int,
        channel_name: str = None,
        platform: str = "twitch",
        exclude_session_id: int = None,
    ) -> Optional[StreamSession]:
        """Active user-only wrapper for the previous session lookup."""
        return self.get_previous_session(
            user_id=user_id,
            session_id=None,
            channel_name=channel_name,
            platform=platform,
            exclude_session_id=exclude_session_id,
        )

    def mark_viewer_attended_user_stream(
        self,
        user_id: int,
        channel_name: str = None,
        platform: str = "twitch",
        viewer_id: str = None,
    ) -> bool:
        """Active user-only wrapper for attendance tracking."""
        return self.mark_viewer_attended_stream(
            user_id=user_id,
            session_id=None,
            channel_name=channel_name,
            platform=platform,
            viewer_id=viewer_id,
        )

    def check_viewer_attended_last_user_stream(
        self,
        user_id: int,
        channel_name: str = None,
        platform: str = "twitch",
        viewer_id: str = None,
    ) -> bool:
        """Active user-only wrapper for previous attendance checks."""
        return self.check_viewer_attended_last_stream(
            user_id=user_id,
            session_id=None,
            channel_name=channel_name,
            platform=platform,
            viewer_id=viewer_id,
        )

    def get_or_create_active_session(
        self,
        user_id: int = None,
        session_id: str = None,
        channel_name: str = None,
        platform: str = "twitch",
        title: str = None,
    ) -> Optional[StreamSession]:
        """Return the active stream session for a channel or create one."""
        if not channel_name:
            return None

        active_session = self.session_repo.get_active_session(
            channel_name=channel_name,
            platform=platform,
            user_id=user_id,
            session_id=session_id,
        )

        if active_session:
            if title and active_session.title != title:
                active_session.title = title
                active_session.updated_at = utcnow_naive()
                self.session_repo.update_session(active_session)

            return active_session

        self._close_old_sessions(
            user_id=user_id,
            session_id=session_id,
            channel_name=channel_name,
            platform=platform,
        )

        new_session = StreamSession(
            user_id=user_id,
            session_id=session_id,
            channel_name=channel_name,
            platform=platform,
            started_at=utcnow_naive(),
            is_active=True,
            title=title,
        )
        self.session_repo.add_session(new_session)

        logger.info("[SESSION] [STREAM SESSION] Created new session for %s (%s)", channel_name, platform)

        return new_session

    def _close_old_sessions(
        self,
        user_id: int = None,
        session_id: str = None,
        channel_name: str = None,
        platform: str = "twitch",
    ):
        """Close previous active sessions for the same channel/platform."""
        old_sessions = self.session_repo.get_old_active_sessions(
            channel_name=channel_name,
            platform=platform,
            user_id=user_id,
            session_id=session_id,
        )

        now = utcnow_naive()
        count = 0
        for session in old_sessions:
            session.is_active = False
            session.ended_at = now
            session.updated_at = now
            self.session_repo.update_session(session)
            count += 1

        if count > 0:
            logger.info("[SECURITY] [STREAM SESSION] Closed %s old sessions for %s (%s)", count, channel_name, platform)

    def end_session(
        self,
        user_id: int = None,
        session_id: str = None,
        channel_name: str = None,
        platform: str = "twitch",
    ) -> bool:
        """End the active stream session for a channel/platform."""
        session = self.session_repo.get_active_session(
            channel_name=channel_name,
            platform=platform,
            user_id=user_id,
            session_id=session_id,
        )

        if session:
            session.is_active = False
            session.ended_at = utcnow_naive()
            session.updated_at = utcnow_naive()
            self.session_repo.update_session(session)
            logger.info("[SECURITY] [STREAM SESSION] Ended session for %s (%s)", channel_name, platform)
            return True

        return False

    def get_last_session(
        self,
        user_id: int = None,
        session_id: str = None,
        channel_name: str = None,
        platform: str = "twitch",
    ) -> Optional[StreamSession]:
        """Return the most recent stream session, active or completed."""
        return self.session_repo.get_last_session(
            channel_name=channel_name,
            platform=platform,
            user_id=user_id,
            session_id=session_id,
        )

    def get_active_session(
        self,
        user_id: int = None,
        session_id: str = None,
        channel_name: str = None,
        platform: str = "twitch",
    ) -> Optional[StreamSession]:
        """Return the active stream session for a channel/platform."""
        return self.session_repo.get_active_session(
            channel_name=channel_name,
            platform=platform,
            user_id=user_id,
            session_id=session_id,
        )

    def get_previous_session(
        self,
        user_id: int = None,
        session_id: str = None,
        channel_name: str = None,
        platform: str = "twitch",
        exclude_session_id: int = None,
    ) -> Optional[StreamSession]:
        """Return the last completed or previous active session for a channel/platform."""
        return self.session_repo.get_previous_session(
            channel_name=channel_name,
            platform=platform,
            user_id=user_id,
            session_id=session_id,
            exclude_session_id=exclude_session_id,
        )

    def mark_viewer_attended_stream(
        self,
        user_id: int = None,
        session_id: str = None,
        channel_name: str = None,
        platform: str = "twitch",
        viewer_id: str = None,
    ) -> bool:
        """Mark that a viewer attended the current stream session."""
        if not viewer_id:
            return False

        active_session = self.get_active_session(
            user_id=user_id,
            session_id=session_id,
            channel_name=channel_name,
            platform=platform,
        )

        if not active_session:
            return False

        streak = self.streak_repo.get_user_streak(
            viewer_id=viewer_id,
            channel_name=channel_name,
            platform=platform,
            user_id=user_id,
            session_id=session_id,
        )

        if streak and streak.last_stream_session_id != active_session.id:
            streak.last_stream_session_id = active_session.id
            streak.last_stream_attended_at = utcnow_naive()
            streak.updated_at = utcnow_naive()
            try:
                self.streak_repo.update_streak(streak)
                logger.debug(
                    "[OK] [STREAM SESSION] Marked viewer %s attended stream session %s",
                    viewer_id,
                    active_session.id,
                )
                return True
            except Exception:
                logger.exception("[ERROR] Error marking viewer attended stream")
                self.db.rollback()
                return False

        return False

    def check_viewer_attended_last_stream(
        self,
        user_id: int = None,
        session_id: str = None,
        channel_name: str = None,
        platform: str = "twitch",
        viewer_id: str = None,
    ) -> bool:
        """Check whether a viewer attended the previous stream session."""
        if not viewer_id:
            return False

        active_session = self.get_active_session(
            user_id=user_id,
            session_id=session_id,
            channel_name=channel_name,
            platform=platform,
        )

        last_session = self.get_previous_session(
            user_id=user_id,
            session_id=session_id,
            channel_name=channel_name,
            platform=platform,
            exclude_session_id=active_session.id if active_session else None,
        )

        if not last_session:
            return True

        streak = self.streak_repo.get_user_streak(
            viewer_id=viewer_id,
            channel_name=channel_name,
            platform=platform,
            user_id=user_id,
            session_id=session_id,
        )

        if not streak:
            return True

        return streak.last_stream_session_id == last_session.id
