# bot_service/repositories/drops_history_repository.py
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, func
from sqlalchemy.exc import IntegrityError

from repositories.base_repository import BaseRepository
from core.database import DropsHistory, UserStreak


class DropsHistoryRepository(BaseRepository[DropsHistory]):
    """
    Repository for DropsHistory and UserStreak entities.
    Handles user streaks and drops history.
    """

    def __init__(self, db: Session):
        super().__init__(DropsHistory, db)

    @staticmethod
    def _owner_scope_filters(model, user_id: int = None, session_id: str = None) -> list[object]:
        """Build user/session owner filters for legacy-compatible tables."""
        filters: list[object] = []
        if user_id is not None:
            filters.append(model.user_id == user_id)
        elif session_id is not None:
            filters.append(model.session_id == session_id)
        return filters

    def get_user_streak_for_user_update(
        self,
        viewer_id: str,
        channel_name: str,
        platform: str,
        user_id: int,
    ) -> Optional[UserStreak]:
        """Get user streak with lock for active user-only runtime."""
        return self.get_user_streak_for_update(
            viewer_id=viewer_id,
            channel_name=channel_name,
            platform=platform,
            user_id=user_id,
            session_id=None,
        )

    def get_user_streak_for_user(
        self,
        viewer_id: str,
        channel_name: str,
        platform: str,
        user_id: int,
    ) -> Optional[UserStreak]:
        """Get user streak for active user-only runtime."""
        return self.get_user_streak(
            viewer_id=viewer_id,
            channel_name=channel_name,
            platform=platform,
            user_id=user_id,
            session_id=None,
        )

    def get_history_for_user(
        self,
        channel_name: str,
        platform: str,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> List[DropsHistory]:
        """Get drops history for a concrete user-owned channel."""
        return self.get_history(
            channel_name=channel_name,
            platform=platform,
            user_id=user_id,
            session_id=None,
            limit=limit,
            offset=offset,
        )

    def count_drops_for_user(
        self,
        channel_name: str,
        platform: str,
        user_id: int,
        lootbox_type: str = None,
        after_date=None,
    ) -> int:
        """Count drops for active user-only runtime."""
        return self.count_drops(
            channel_name=channel_name,
            platform=platform,
            user_id=user_id,
            session_id=None,
            lootbox_type=lootbox_type,
            after_date=after_date,
        )

    def count_legendary_drops_for_user(
        self,
        channel_name: str,
        platform: str,
        user_id: int,
    ) -> int:
        """Count legendary drops for a user-owned channel."""
        return self.count_legendary_drops(
            channel_name=channel_name,
            platform=platform,
            user_id=user_id,
            session_id=None,
        )

    def get_active_mythical_session_for_user(
        self,
        channel_name: str,
        now_time,
        user_id: int,
    ):
        """Get active mythical session for active user-only runtime."""
        return self.get_active_mythical_session(
            channel_name=channel_name,
            now_time=now_time,
            user_id=user_id,
            session_id=None,
        )

    # === UserStreak ===

    def get_user_streak_for_update(
        self,
        viewer_id: str,
        channel_name: str,
        platform: str,
        user_id: int = None,
        session_id: str = None,
    ) -> Optional[UserStreak]:
        """Get user streak record with pessimistic lock."""
        filters = [
            UserStreak.viewer_id == viewer_id,
            UserStreak.channel_name == channel_name,
            UserStreak.platform == platform,
        ]

        owner_filters = self._owner_scope_filters(UserStreak, user_id=user_id, session_id=session_id)
        if not owner_filters:
            return None
        filters.extend(owner_filters)

        return (
            self.db.query(UserStreak).filter(and_(*filters)).with_for_update().first()
        )

    def get_user_streak(
        self,
        viewer_id: str,
        channel_name: str,
        platform: str,
        user_id: int = None,
        session_id: str = None,
    ) -> Optional[UserStreak]:
        """Get user streak record."""
        filters = [
            UserStreak.viewer_id == viewer_id,
            UserStreak.channel_name == channel_name,
            UserStreak.platform == platform,
        ]

        owner_filters = self._owner_scope_filters(UserStreak, user_id=user_id, session_id=session_id)
        if not owner_filters:
            return None
        filters.extend(owner_filters)

        return self.db.query(UserStreak).filter(and_(*filters)).first()

    def update_streak(self, streak: UserStreak) -> UserStreak:
        """Update streak record."""
        self.db.commit()
        self.db.refresh(streak)
        return streak

    def add_streak(self, streak: UserStreak) -> UserStreak:
        """Add new streak record."""
        self.db.add(streak)
        self.db.commit()
        self.db.refresh(streak)
        return streak

    def create_history_entry(
        self,
        user_id: int = None,
        session_id: str = None,
        channel_name: str = None,
        platform: str = None,
        viewer_id: str = None,
        viewer_name: str = None,
        lootbox_type: str = None,
        quality_id: int = None,
        reward_id: int = None,
        reward_name: str = None,
        reward_type: str = None,
        reward_value: str = None,
        donation_amount: float = None,
        streak_days: int = None,
        messages_count: int = None,
        stream_session_id: int = None,
        source_event_id: str = None,
        donation_alert_id: str = None,
        chat_message_id: int = None,
    ) -> DropsHistory:
        """Create a new drops history entry."""
        entry, _ = self.get_or_create_history_entry(
            user_id=user_id,
            session_id=session_id,
            channel_name=channel_name,
            platform=platform,
            viewer_id=viewer_id,
            viewer_name=viewer_name,
            lootbox_type=lootbox_type,
            quality_id=quality_id,
            reward_id=reward_id,
            reward_name=reward_name,
            reward_type=reward_type,
            reward_value=reward_value,
            donation_amount=donation_amount,
            streak_days=streak_days,
            messages_count=messages_count,
            stream_session_id=stream_session_id,
            source_event_id=source_event_id,
            donation_alert_id=donation_alert_id,
            chat_message_id=chat_message_id,
        )
        return entry

    def get_or_create_history_entry(
        self,
        user_id: int = None,
        session_id: str = None,
        channel_name: str = None,
        platform: str = None,
        viewer_id: str = None,
        viewer_name: str = None,
        lootbox_type: str = None,
        quality_id: int = None,
        reward_id: int = None,
        reward_name: str = None,
        reward_type: str = None,
        reward_value: str = None,
        donation_amount: float = None,
        streak_days: int = None,
        messages_count: int = None,
        stream_session_id: int = None,
        source_event_id: str = None,
        donation_alert_id: str = None,
        chat_message_id: int = None,
    ) -> tuple[DropsHistory, bool]:
        """Create a drops history entry once per external source event."""
        existing_entry = self.get_history_by_source_event_id(
            source_event_id=source_event_id,
            channel_name=channel_name,
            platform=platform,
            user_id=user_id,
            session_id=session_id,
        )
        if existing_entry:
            return existing_entry, False

        entry = DropsHistory(
            user_id=user_id,
            session_id=session_id,
            channel_name=channel_name,
            platform=platform,
            viewer_id=viewer_id,
            viewer_name=viewer_name,
            lootbox_type=lootbox_type,
            quality_id=quality_id,
            reward_id=reward_id,
            reward_name=reward_name,
            reward_type=reward_type,
            reward_value=reward_value,
            donation_amount=donation_amount,
            streak_days=streak_days,
            messages_count=messages_count,
            stream_session_id=stream_session_id,
            source_event_id=source_event_id,
            donation_alert_id=donation_alert_id,
            chat_message_id=chat_message_id,
        )
        self.db.add(entry)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing_entry = self.get_history_by_source_event_id(
                source_event_id=source_event_id,
                channel_name=channel_name,
                platform=platform,
                user_id=user_id,
                session_id=session_id,
            )
            if existing_entry:
                return existing_entry, False
            raise
        self.db.refresh(entry)
        return entry, True

    def get_history_by_source_event_id(
        self,
        source_event_id: str,
        channel_name: str,
        platform: str,
        user_id: int = None,
        session_id: str = None,
    ) -> Optional[DropsHistory]:
        """Return an existing history row for a stable external event identifier."""
        if not source_event_id:
            return None

        query = self.db.query(DropsHistory).filter(
            DropsHistory.channel_name == channel_name,
            DropsHistory.platform == platform,
            DropsHistory.source_event_id == source_event_id,
        )

        owner_filters = self._owner_scope_filters(
            DropsHistory,
            user_id=user_id,
            session_id=session_id,
        )
        if not owner_filters:
            return None

        return query.filter(and_(*owner_filters)).first()

    # === DropsHistory ===

    # === DropsHistory ===

    def get_history(
        self,
        channel_name: str,
        platform: str,
        user_id: int = None,
        session_id: str = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[DropsHistory]:
        query = self.db.query(DropsHistory).filter(
            DropsHistory.channel_name == channel_name, DropsHistory.platform == platform
        )

        owner_filters = self._owner_scope_filters(DropsHistory, user_id=user_id, session_id=session_id)
        if not owner_filters:
            return []  # Requirement from service logic
        query = query.filter(and_(*owner_filters))

        return (
            query.order_by(desc(DropsHistory.created_at))
            .offset(offset)
            .limit(limit)
            .all()
        )

    def count_drops(
        self,
        channel_name: str,
        platform: str,
        user_id: int = None,
        session_id: str = None,
        lootbox_type: str = None,
        after_date=None,
    ) -> int:
        query = self.db.query(func.count(DropsHistory.id)).filter(
            DropsHistory.channel_name == channel_name, DropsHistory.platform == platform
        )
        owner_filters = self._owner_scope_filters(DropsHistory, user_id=user_id, session_id=session_id)
        if owner_filters:
            query = query.filter(and_(*owner_filters))

        if lootbox_type:
            query = query.filter(DropsHistory.lootbox_type == lootbox_type)

        if after_date:
            query = query.filter(DropsHistory.created_at >= after_date)

        return query.scalar() or 0

    def get_channel_stats(self, user_id: int, channel_name: str, platform: str):
        """Aggregate stats using SQL"""
        base_filter = and_(
            DropsHistory.user_id == user_id,
            DropsHistory.channel_name == channel_name,
            DropsHistory.platform == platform,
        )

        # This mirrors get_full_channel_stats aggregation
        # We can expose flexible methods or specific ones.
        return self.db.query(DropsHistory).filter(base_filter)

    def count_legendary_drops(
        self,
        channel_name: str,
        platform: str,
        user_id: int = None,
        session_id: str = None,
    ):
        """Count drops with Legendary quality."""
        from models.drops import DropsQuality

        query = (
            self.db.query(func.count(DropsHistory.id))
            .join(DropsQuality)
            .filter(
                DropsHistory.channel_name == channel_name,
                DropsHistory.platform == platform,
                DropsQuality.name == "Legendary",
            )
        )
        owner_filters = self._owner_scope_filters(DropsHistory, user_id=user_id, session_id=session_id)
        if owner_filters:
            query = query.filter(and_(*owner_filters))
        return query.scalar() or 0

    def get_top_viewers(
        self, user_id: int, channel_name: str, platform: str, limit: int = 10
    ):
        return (
            self.db.query(
                DropsHistory.viewer_name,
                func.count(DropsHistory.id).label("drops_count"),
            )
            .filter(
                DropsHistory.user_id == user_id,
                DropsHistory.channel_name == channel_name,
                DropsHistory.platform == platform,
            )
            .group_by(DropsHistory.viewer_name)
            .order_by(func.count(DropsHistory.id).desc())
            .limit(limit)
            .all()
        )

    def get_streaks_paginated(
        self,
        user_id: int,
        channel_name: str,
        platform: str = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[UserStreak]:
        query = self.db.query(UserStreak).filter(
            UserStreak.user_id == user_id, UserStreak.channel_name == channel_name
        )
        if platform:
            query = query.filter(UserStreak.platform == platform)

        return (
            query.order_by(desc(UserStreak.current_streak))
            .offset(offset)
            .limit(limit)
            .all()
        )

    def reset_channel_streaks(self, user_id: int, channel_name: str) -> int:
        deleted = (
            self.db.query(UserStreak)
            .filter(
                UserStreak.user_id == user_id, UserStreak.channel_name == channel_name
            )
            .delete(synchronize_session=False)
        )
        self.db.commit()
        return deleted

    # === Mythical ===
    from models.drops import (
        MythicalDropsSession,
    )  # Deferred import or use string if model in same base?
    # Better to import at top if possible, or use 'MythicalDropsSession' if available in scope.
    # It's not imported at top of file currently.

    def get_active_mythical_session(
        self, channel_name: str, now_time, user_id: int = None, session_id: str = None
    ):
        # We need to import MythicalDropsSession.
        # Check imports at top.
        from models.drops import MythicalDropsSession

        query = self.db.query(MythicalDropsSession).filter(
            MythicalDropsSession.channel_name == channel_name,
            MythicalDropsSession.is_active == True,
            MythicalDropsSession.expires_at > now_time,
        )

        owner_filters = self._owner_scope_filters(
            MythicalDropsSession,
            user_id=user_id,
            session_id=session_id,
        )
        if not owner_filters:
            return None
        query = query.filter(and_(*owner_filters))

        return query.first()

    def add_mythical_session(
        self, session: MythicalDropsSession
    ) -> MythicalDropsSession:
        """Add new mythical drops session."""
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def update_mythical_session(
        self, session: MythicalDropsSession
    ) -> MythicalDropsSession:
        """Update mythical drops session."""
        self.db.commit()
        self.db.refresh(session)
        return session
