# bot_service/repositories/youtube_queue_repository.py
"""
Repository for YouTube Queue operations.
Follows Clean Architecture - all db.query calls encapsulated here.
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, asc, func

from repositories.base_repository import BaseRepository
from core.database import YouTubeQueue


class YouTubeQueueRepository(BaseRepository[YouTubeQueue]):
    """
    Repository for YouTubeQueue entity.
    Handles queue item CRUD and queue-specific queries.
    """
    def __init__(self, db: Session):
        super().__init__(YouTubeQueue, db)

    # === Queue Item Queries ===

    def _scope_filters(
        self,
        user_id: int | None = None,
        session_id: str | None = None,
    ) -> list[object]:
        """Build queue scope filters for user or legacy session compat."""
        filters: list[object] = []
        if user_id is not None:
            filters.append(YouTubeQueue.user_id == user_id)
        if session_id is not None:
            filters.append(YouTubeQueue.session_id == session_id)
        return filters

    def get_pending_by_video_id_for_user(
        self,
        video_id: str,
        user_id: int,
    ) -> Optional[YouTubeQueue]:
        """Check if video already exists in pending queue for a user."""
        return self.get_pending_by_video_id(video_id=video_id, user_id=user_id)

    def get_banned_by_video_id_for_user(
        self,
        video_id: str,
        user_id: int,
    ) -> Optional[YouTubeQueue]:
        """Check if video is banned for a user queue."""
        return self.get_banned_by_video_id(video_id=video_id, user_id=user_id)

    def get_pending_by_video_id_all_for_user(
        self,
        video_id: str,
        user_id: int,
    ) -> List[YouTubeQueue]:
        """Get all pending queue items for a user by video id."""
        return self.get_pending_by_video_id_all(video_id=video_id, user_id=user_id)

    def count_pending_for_user(self, user_id: int) -> int:
        """Count pending queue items for a user."""
        return self.count_pending(user_id=user_id)

    def get_pending_queue_for_user(self, user_id: int) -> List[YouTubeQueue]:
        """Get pending queue for a user ordered by position."""
        return self.get_pending_queue(user_id=user_id)

    def get_pending_by_video_id(
        self,
        video_id: str,
        user_id: int = None,
        session_id: str = None
    ) -> Optional[YouTubeQueue]:
        """Check if video already in pending queue."""
        filters = [
            YouTubeQueue.video_id == video_id,
            YouTubeQueue.status == 'pending'
        ]
        filters.extend(self._scope_filters(user_id=user_id, session_id=session_id))

        return self.db.query(YouTubeQueue).filter(and_(*filters)).first()

    def get_banned_by_video_id(
        self,
        video_id: str,
        user_id: int = None,
        session_id: str = None
    ) -> Optional[YouTubeQueue]:
        """Check if video is banned for this user/session."""
        filters = [
            YouTubeQueue.video_id == video_id,
            YouTubeQueue.status == 'banned'
        ]
        filters.extend(self._scope_filters(user_id=user_id, session_id=session_id))

        return self.db.query(YouTubeQueue).filter(and_(*filters)).first()

    def get_pending_by_video_id_all(
        self,
        video_id: str,
        user_id: int = None,
        session_id: str = None
    ) -> List[YouTubeQueue]:
        """Get all pending items by video_id for user/session."""
        filters = [
            YouTubeQueue.video_id == video_id,
            YouTubeQueue.status == 'pending'
        ]
        filters.extend(self._scope_filters(user_id=user_id, session_id=session_id))

        return self.db.query(YouTubeQueue).filter(and_(*filters)).all()

    def count_pending(
        self,
        user_id: int = None,
        session_id: str = None
    ) -> int:
        """Count pending items in queue."""
        filters = [YouTubeQueue.status == 'pending']
        filters.extend(self._scope_filters(user_id=user_id, session_id=session_id))

        return self.db.query(YouTubeQueue).filter(and_(*filters)).count()

    def get_pending_queue(
        self,
        user_id: int = None,
        session_id: str = None
    ) -> List[YouTubeQueue]:
        """Get pending queue items ordered by position."""
        filters = [YouTubeQueue.status == 'pending']
        filters.extend(self._scope_filters(user_id=user_id, session_id=session_id))

        return (
            self.db.query(YouTubeQueue)
            .filter(and_(*filters))
            .order_by(asc(YouTubeQueue.position))
            .all()
        )

    def get_pending_item(
        self,
        queue_id: int,
        user_id: int
    ) -> Optional[YouTubeQueue]:
        """Get specific pending queue item."""
        return self.db.query(YouTubeQueue).filter(
            and_(
                YouTubeQueue.id == queue_id,
                YouTubeQueue.user_id == user_id,
                YouTubeQueue.status == 'pending'
            )
        ).first()

    def get_item_by_id(
        self,
        queue_id: int,
        user_id: int
    ) -> Optional[YouTubeQueue]:
        """Get queue item by ID (any status)."""
        return self.db.query(YouTubeQueue).filter(
            and_(
                YouTubeQueue.id == queue_id,
                YouTubeQueue.user_id == user_id
            )
        ).first()

    def get_next_pending(self, user_id: int) -> Optional[YouTubeQueue]:
        """Get next pending video (first in position order)."""
        return (
            self.db.query(YouTubeQueue)
            .filter(
                and_(
                    YouTubeQueue.user_id == user_id,
                    YouTubeQueue.status == 'pending'
                )
            )
            .order_by(asc(YouTubeQueue.position))
            .first()
        )

    def get_last_pending_by_requester(
        self,
        user_id: int,
        requester_id: str,
        platform: str
    ) -> Optional[YouTubeQueue]:
        """Get last pending video added by specific requester."""
        return (
            self.db.query(YouTubeQueue)
            .filter(
                and_(
                    YouTubeQueue.user_id == user_id,
                    YouTubeQueue.requester_id == requester_id,
                    YouTubeQueue.platform == platform,
                    YouTubeQueue.status == 'pending'
                )
            )
            .order_by(desc(YouTubeQueue.added_at))
            .first()
        )

    def get_all_pending_for_user(self, user_id: int) -> List[YouTubeQueue]:
        """Get all pending items for a user (used for clear queue)."""
        return (
            self.db.query(YouTubeQueue)
            .filter(
                and_(
                    YouTubeQueue.user_id == user_id,
                    YouTubeQueue.status == 'pending'
                )
            )
            .all()
        )

    def get_pending_ordered(self, user_id: int) -> List[YouTubeQueue]:
        """Get pending items ordered by position (for rebuild positions)."""
        return (
            self.db.query(YouTubeQueue)
            .filter(
                and_(
                    YouTubeQueue.user_id == user_id,
                    YouTubeQueue.status == 'pending'
                )
            )
            .order_by(asc(YouTubeQueue.position))
            .all()
        )

    # === Queue Item Mutations ===

    def add_item(self, item: YouTubeQueue) -> YouTubeQueue:
        """Add new item to queue."""
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_status(
        self,
        item: YouTubeQueue,
        status: str,
        played_at=None
    ) -> YouTubeQueue:
        """Update item status."""
        item.status = status
        if played_at:
            item.played_at = played_at
        self.db.commit()
        return item

    def rebuild_positions(self, items: List[YouTubeQueue]) -> None:
        """Rebuild positions for list of items."""
        for i, item in enumerate(items):
            item.position = i + 1
        # Commit handled by caller for transaction safety
