# features/drops/drops_service.py
"""
Unified Drops Service aggregating all logic via Mixins.
Replaces the old monolithic service.
"""

from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Dict, Any, List, Optional

from core.database import (
    DropsHistory,
    DropsQuality,
    DropsConfig,
    UserStreak,
    MythicalDropsSession,
)
from core.datetime_utils import utcnow_naive

# Import Mixins (Keeping imports for now if they are used for typing or other reasons,
# though we are overriding methods)
from .drops_config_service import DropsConfigMixin
from .drops_streak_service import DropsStreakMixin
from .drops_mythical_service import DropsMythicalMixin

from repositories.drops_config_repository import DropsConfigRepository
from repositories.drops_history_repository import DropsHistoryRepository


class DropsService(DropsConfigMixin, DropsStreakMixin, DropsMythicalMixin):
    """Unified Service for Drops system management

    Inherits functionality from:
    - DropsConfigMixin: Config, Rewards, History helpers
    - DropsStreakMixin: User Streaks, Streak/Donation processing
    - DropsMythicalMixin: Mythical Drops session/logic
    """

    def __init__(self, db: Session):
        self.db = db
        # Repositories
        self.config_repo = DropsConfigRepository(db)
        self.history_repo = DropsHistoryRepository(db)

    # === Quality Methods ===

    def get_all_qualities(self) -> List[Dict[str, Any]]:
        """Get all drop qualities."""
        qualities = self.config_repo.get_all_qualities()
        return [
            {"id": q.id, "name": q.name, "color": q.color, "weight": q.weight}
            for q in qualities
        ]

    def get_quality_by_name(self, name: str) -> Optional[DropsQuality]:
        """Get quality by name."""
        return self.config_repo.get_quality_by_name(name)

    def get_qualities_by_ids(self, ids: List[int]) -> Dict[int, Dict]:
        """Get qualities by IDs as dict."""
        qualities = self.config_repo.get_qualities_by_ids(ids)
        return {q.id: {"name": q.name, "color": q.color, "id": q.id} for q in qualities}

    # === Config Methods ===

    def get_config_by_user_id(self, user_id: int) -> Optional[DropsConfig]:
        """Get drops config by user ID."""
        return self.config_repo.get_by_user(user_id)

    def get_config_by_widget_token(self, token: str) -> Optional[DropsConfig]:
        """Get drops config by widget token."""
        return self.config_repo.get_by_widget_token(token)

    # === History Methods ===

    def get_drops_history(
        self,
        user_id: int = None,
        session_id: str = None,
        channel_name: str = None,
        platform: str = "twitch",
        limit: int = 50,
        offset: int = 0,
    ) -> List[DropsHistory]:
        """Get drops history."""
        return self.history_repo.get_history(
            channel_name, platform, user_id, session_id, limit, offset
        )

    def get_drops_stats(
        self,
        user_id: int = None,
        session_id: str = None,
        channel_name: str = None,
        platform: str = "twitch",
    ) -> Dict[str, Any]:
        """Get drops statistics."""
        # Using count_drops helper might be inefficient if we do multiple queries,
        # but robust. Or we can add specific stats method to repo.

        # Let's use basic counts if we didn't implement complex stats in repo yet,
        # OR better: use count_drops from repo.

        total_drops = self.history_repo.count_drops(
            channel_name, platform, user_id, session_id
        )

        today = utcnow_naive().date()
        today_drops = self.history_repo.count_drops(
            channel_name, platform, user_id, session_id, after_date=today
        )

        legendary_drops = self.history_repo.count_legendary_drops(
            channel_name, platform, user_id, session_id
        )
        mythical_drops = self.history_repo.count_drops(
            channel_name, platform, user_id, session_id, lootbox_type="mythical"
        )

        # Keep both key styles for backward compatibility with existing clients/tests.
        return {
            "total_drops": total_drops,
            "today_drops": today_drops,
            "legendary_drops": legendary_drops,
            "mythical_drops": mythical_drops,
            "totalDrops": total_drops,
            "todayDrops": today_drops,
            "legendaryDrops": legendary_drops,
            "mythicalDrops": mythical_drops,
        }

    def get_full_channel_stats(
        self, user_id: int, channel_name: str, platform: str
    ) -> Dict[str, Any]:
        """Get comprehensive stats for a channel."""
        # This one used get_channel_stats in repo which returns query object (not ideal but flexible).
        # Actually I made get_channel_stats return query in repo.
        # So I can just chain .count() here? Yes, but accessing db object via repo return is leaky.
        # But acceptable for complex stats.

        # However, it's better to use specific methods.
        total = self.history_repo.count_drops(channel_name, platform, user_id=user_id)
        streak = self.history_repo.count_drops(
            channel_name, platform, user_id=user_id, lootbox_type="streak"
        )
        donation = self.history_repo.count_drops(
            channel_name, platform, user_id=user_id, lootbox_type="donation"
        )
        mythical = self.history_repo.count_drops(
            channel_name, platform, user_id=user_id, lootbox_type="mythical"
        )

        top_viewers_data = self.history_repo.get_top_viewers(
            user_id, channel_name, platform
        )

        return {
            "total_drops": total,
            "streak_drops": streak,
            "donation_drops": donation,
            "mythical_drops": mythical,
            "top_viewers": [
                {"viewer_name": v, "drops_count": c} for v, c in top_viewers_data
            ],
        }

    # === Streak Methods ===

    def get_user_streaks_paginated(
        self,
        user_id: int,
        channel_name: str,
        platform: str = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict]:
        """Get paginated user streaks."""
        streaks = self.history_repo.get_streaks_paginated(
            user_id, channel_name, platform, limit, offset
        )
        return [
            {
                "viewer_name": s.viewer_name,
                "current_streak": s.current_streak,
                "max_streak": s.max_streak,
                "messages_this_stream": s.messages_this_stream,
                "last_activity": s.last_activity,
            }
            for s in streaks
        ]

    def reset_channel_streaks(self, user_id: int, channel_name: str) -> int:
        """Reset all streaks for a channel. Returns deleted count."""
        return self.history_repo.reset_channel_streaks(user_id, channel_name)

    # === Mythical Session Methods ===

    def get_active_mythical_session(
        self, user_id: int = None, session_id: str = None, channel_name: str = None
    ) -> Optional[Dict]:
        """Get active mythical drops session."""
        now = utcnow_naive()
        session = self.history_repo.get_active_mythical_session(
            channel_name, now, user_id, session_id
        )

        if not session:
            return None

        time_remaining = max(0, int((session.expires_at - now).total_seconds()))

        return {
            "id": session.id,
            "is_active": session.is_active,
            "donation_amount": session.donation_amount,
            "window_duration_minutes": session.window_duration_minutes,
            "started_at": session.started_at.isoformat()
            if session.started_at
            else None,
            "expires_at": session.expires_at.isoformat()
            if session.expires_at
            else None,
            "time_remaining_seconds": time_remaining,
            "time_remaining_minutes": int(time_remaining / 60),
            "time_remaining_formatted": f"{int(time_remaining / 60)}:{time_remaining % 60:02d}",
        }

    def get_active_user_mythical_session(
        self,
        user_id: int,
        channel_name: str = None,
    ) -> Optional[Dict]:
        """Active user-only wrapper for mythical session lookup."""
        return self.get_active_mythical_session(
            user_id=user_id,
            session_id=None,
            channel_name=channel_name,
        )
