# features/drops/drops_streak_service.py
"""Drops Streak management and Donation/Streak event processing"""
import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from core.database import PendingStreakChest, UserStreak, DropsConfig
from core.datetime_utils import utcnow_naive
from services.stream_session_service import StreamSessionService
from repositories.drops_history_repository import DropsHistoryRepository

logger = logging.getLogger(__name__)

_QUALITY_RANK = {
    "Common": 1,
    "Rare": 2,
    "Epic": 3,
    "Legendary": 4,
    "Mythical": 5,
}


class DropsStreakMixin:
    """Mixin for User Streak management and Streak/Donation event processing
    
    Requires DropsConfigMixin for config and reward methods.
    Assumes self.db and self.history_repo are available (provided by DropsService).
    """

    # self.db must be available in the usage class
    db: Session
    # We expect history_repo to be available or we create it
    history_repo: Optional[DropsHistoryRepository] = None

    # Expected methods from DropsConfigMixin
    def get_config(self, **kwargs): pass
    def get_quality_by_name(self, name): pass
    def _get_random_reward(self, **kwargs): pass
    def _record_drops_history(self, **kwargs): pass
    def _normalize_source_event_id(self, **kwargs): pass
    
    # Expected method from DropsMythicalMixin or self
    def _check_stream_online(self, **kwargs): pass
    
    def _ensure_repo(self):
        if not getattr(self, 'history_repo', None):
             self.history_repo = DropsHistoryRepository(self.db)
        return self.history_repo

    def _get_pending_streak_chest(
        self,
        *,
        user_id: int = None,
        session_id: str = None,
        channel_name: str,
        platform: str,
        viewer_id: str,
    ) -> Optional[PendingStreakChest]:
        query = self.db.query(PendingStreakChest).filter(
            PendingStreakChest.channel_name == channel_name,
            PendingStreakChest.platform == platform,
            PendingStreakChest.viewer_id == viewer_id,
            PendingStreakChest.status == "pending",
        )
        if user_id is not None:
            query = query.filter(PendingStreakChest.user_id == user_id)
        else:
            query = query.filter(PendingStreakChest.session_id == session_id)
        return query.first()

    def _quality_rank(self, quality_name: str) -> int:
        return _QUALITY_RANK.get(quality_name, 0)

    def _resolve_stream_session_id(
        self,
        user_id: int = None,
        session_id: str = None,
        channel_name: str = None,
        platform: str = "twitch",
        stream_session_id: int = None,
        create_if_online: bool = False,
    ) -> Optional[int]:
        """Resolve the stream session used for reward history linkage."""
        if stream_session_id is not None:
            return stream_session_id

        stream_session_service = StreamSessionService(self.db)
        active_session = stream_session_service.get_active_session(
            user_id=user_id,
            session_id=session_id,
            channel_name=channel_name,
            platform=platform,
        )
        if active_session:
            return active_session.id

        if create_if_online and self._check_stream_online(
            user_id=user_id,
            session_id=session_id,
            channel_name=channel_name,
            platform=platform,
        ):
            active_session = stream_session_service.get_or_create_active_session(
                user_id=user_id,
                session_id=session_id,
                channel_name=channel_name,
                platform=platform,
            )
            if active_session:
                return active_session.id

        return None

    def get_user_streak_for_user(
        self,
        user_id: int,
        channel_name: str = None,
        platform: str = "twitch",
        viewer_id: str = None,
    ) -> Optional[UserStreak]:
        """Active user-only wrapper for streak lookup."""
        return self.get_user_streak(
            user_id=user_id,
            session_id=None,
            channel_name=channel_name,
            platform=platform,
            viewer_id=viewer_id,
        )

    def update_user_streak_for_user(
        self,
        user_id: int,
        channel_name: str = None,
        platform: str = "twitch",
        viewer_id: str = None,
        viewer_name: str = None,
        is_streaming: bool = True,
    ) -> UserStreak:
        """Active user-only wrapper for streak updates."""
        return self.update_user_streak(
            user_id=user_id,
            session_id=None,
            channel_name=channel_name,
            platform=platform,
            viewer_id=viewer_id,
            viewer_name=viewer_name,
            is_streaming=is_streaming,
        )

    def increment_viewer_message_count_for_user(
        self,
        user_id: int,
        channel_name: str = None,
        platform: str = "twitch",
        viewer_id: str = None,
        viewer_name: str = None,
    ) -> UserStreak:
        """Active user-only wrapper for per-viewer message counters."""
        return self.increment_viewer_message_count(
            user_id=user_id,
            session_id=None,
            channel_name=channel_name,
            platform=platform,
            viewer_id=viewer_id,
            viewer_name=viewer_name,
        )

    def process_streak_drops_for_user(
        self,
        user_id: int,
        channel_name: str = None,
        platform: str = "twitch",
        viewer_id: str = None,
        viewer_name: str = None,
        source_event_id: str = None,
        chat_message_id: int = None,
        stream_session_id: int = None,
    ) -> Optional[Dict[str, Any]]:
        """Active user-only wrapper for streak drops processing."""
        return self.process_streak_drops(
            user_id=user_id,
            session_id=None,
            channel_name=channel_name,
            platform=platform,
            viewer_id=viewer_id,
            viewer_name=viewer_name,
            source_event_id=source_event_id,
            chat_message_id=chat_message_id,
            stream_session_id=stream_session_id,
        )

    def process_donation_drops_for_user(
        self,
        user_id: int,
        channel_name: str = None,
        platform: str = "twitch",
        viewer_id: str = None,
        viewer_name: str = None,
        donation_amount: float = None,
        source_event_id: str = None,
        donation_alert_id: str = None,
        stream_session_id: int = None,
    ) -> Optional[Dict[str, Any]]:
        """Active user-only wrapper for donation drops processing."""
        return self.process_donation_drops(
            user_id=user_id,
            session_id=None,
            channel_name=channel_name,
            platform=platform,
            viewer_id=viewer_id,
            viewer_name=viewer_name,
            donation_amount=donation_amount,
            source_event_id=source_event_id,
            donation_alert_id=donation_alert_id,
            stream_session_id=stream_session_id,
        )

    def get_user_streak(self, user_id: int = None, session_id: str = None, channel_name: str = None, platform: str = "twitch", viewer_id: str = None) -> Optional[UserStreak]:
        """Get the viewer streak record."""
        repo = self._ensure_repo()
        return repo.get_user_streak(viewer_id, channel_name, platform, user_id, session_id)

    def update_user_streak(self, user_id: int = None, session_id: str = None, channel_name: str = None, platform: str = "twitch", viewer_id: str = None, viewer_name: str = None, is_streaming: bool = True) -> UserStreak:
        """Update the viewer streak record."""
        config = self.get_config(user_id=user_id, session_id=session_id, channel_name=channel_name, platform=None)
        if not config:
            logger.warning(f"No config found for streak update: channel={channel_name}, viewer={viewer_name}")
            return None

        repo = self._ensure_repo()
        # Pessimistic locking to prevent race conditions
        streak = repo.get_user_streak_for_update(viewer_id, channel_name, platform, user_id, session_id)
        
        if not streak:
            streak = UserStreak(
                user_id=user_id,
                session_id=session_id,
                channel_name=channel_name,
                platform=platform,
                viewer_id=viewer_id,
                viewer_name=viewer_name,
                messages_this_stream=0
            )
            # Add early to session if needed for lock? No, add later is fine.
            repo.add_streak(streak) # This adds and commits.
            # But wait, we want to hold the transaction if we were locking?
            # If we just created it, we don't hold a lock on a row that didn't exist.
            # But add_streak commits.
            pass

        now = utcnow_naive()
        stream_session_service = StreamSessionService(self.db)

        # Check online status using the helper method (assumed to be available in class)
        is_stream_online = self._check_stream_online(user_id=user_id, session_id=session_id, channel_name=channel_name, platform=platform)

        if not is_stream_online:
            streak.last_activity = now
            streak.updated_at = now
            repo.update_streak(streak) # commits
            return streak

        active_session = stream_session_service.get_or_create_active_session(
            user_id=user_id,
            session_id=session_id,
            channel_name=channel_name,
            platform=platform
        )

        if not active_session:
            streak.last_activity = now
            streak.updated_at = now
            repo.update_streak(streak)
            return streak

        previous_stream_session_id = streak.last_stream_session_id
        is_new_stream = previous_stream_session_id != active_session.id

        if is_new_stream:
            previous_session = stream_session_service.get_previous_session(
                user_id=user_id,
                session_id=session_id,
                channel_name=channel_name,
                platform=platform,
                exclude_session_id=active_session.id,
            )

            if previous_stream_session_id is None and previous_session is None:
                attended_previous = True
            else:
                attended_previous = (
                    previous_session is not None
                    and previous_stream_session_id == previous_session.id
                )

            if attended_previous and streak.messages_this_stream >= config.streak_messages_required:
                streak.current_streak += 1
                streak.max_streak = max(streak.max_streak, streak.current_streak)
                logger.info(f"[OK] Streak +1 for {viewer_name}: {streak.current_streak} (messages: {streak.messages_this_stream}/{config.streak_messages_required})")
            elif not attended_previous:
                if config.streak_reset_on_skip and streak.current_streak > 0:
                    logger.info(f"[ERROR] Streak reset for {viewer_name}: skipped stream")
                    streak.current_streak = 0
                else:
                    logger.info(f"[STREAK] Streak paused for {viewer_name}: skipped stream (reset disabled)")
            else:
                if config.streak_reset_on_skip and streak.current_streak > 0:
                    logger.info(f"[ERROR] Streak reset for {viewer_name}: insufficient messages")
                    streak.current_streak = 0
                else:
                    logger.info(f"[STREAK] Streak paused for {viewer_name}: insufficient messages (reset disabled)")

            streak.messages_this_stream = 0

        streak.last_stream_session_id = active_session.id
        streak.last_stream_attended_at = now
        streak.last_activity = now
        streak.updated_at = now

        try:
            repo.update_streak(streak)
        except Exception:
            logger.exception("[ERROR] Error updating streak for {viewer_name}")
            self.db.rollback()
            raise

        return streak

    def increment_viewer_message_count(self, user_id: int = None, session_id: str = None, channel_name: str = None, platform: str = "twitch", viewer_id: str = None, viewer_name: str = None) -> UserStreak:
        """Increment the viewer message counter for the current stream."""
        repo = self._ensure_repo()
        # We should use locking if concurrent updates likely, but simple increment usually ok.
        # But get_user_streak might suffice.
        streak = self.get_user_streak(user_id=user_id, session_id=session_id, channel_name=channel_name, platform=platform, viewer_id=viewer_id)

        if not streak:
            streak = UserStreak(
                user_id=user_id,
                session_id=session_id,
                channel_name=channel_name,
                platform=platform,
                viewer_id=viewer_id,
                viewer_name=viewer_name,
                messages_this_stream=1,
                current_streak=0,
                max_streak=0
            )
            repo.add_streak(streak)
        else:
            streak.messages_this_stream += 1
            streak.last_activity = utcnow_naive()
            streak.updated_at = utcnow_naive()
            repo.update_streak(streak)

        return streak

    def process_streak_drops(self, user_id: int = None, session_id: str = None, channel_name: str = None, platform: str = "twitch", viewer_id: str = None, viewer_name: str = None, source_event_id: str = None, chat_message_id: int = None, stream_session_id: int = None) -> Optional[Dict[str, Any]]:
        """Process streak drops."""
        config = self.get_config(user_id=user_id, session_id=session_id, channel_name=channel_name, platform=None)
        if not config:
            return None

        streak_enabled = False
        if platform == "twitch":
            streak_enabled = getattr(config, 'streak_enabled_twitch', False)
        elif platform == "vk":
            streak_enabled = getattr(config, 'streak_enabled_vk', False)

        if not streak_enabled:
            return None

        normalized_source_event_id = self._normalize_source_event_id(
            source_event_id=source_event_id,
            chat_message_id=chat_message_id,
        )
        if normalized_source_event_id:
            existing_history = self._ensure_repo().get_history_by_source_event_id(
                source_event_id=normalized_source_event_id,
                channel_name=channel_name,
                platform=platform,
                user_id=user_id,
                session_id=session_id,
            )
            if existing_history:
                logger.info(
                    "[DROPS] Duplicate streak event skipped for %s (%s)",
                    viewer_name,
                    normalized_source_event_id,
                )
                return None

        streak = self.update_user_streak(user_id=user_id, session_id=session_id, channel_name=channel_name, platform=platform, viewer_id=viewer_id, viewer_name=viewer_name)

        quality_name = self._get_streak_quality(streak.current_streak, config)
        if not quality_name:
            return None

        quality = self.get_quality_by_name(quality_name)
        if not quality:
            return None

        resolved_stream_session_id = self._resolve_stream_session_id(
            user_id=user_id,
            session_id=session_id,
            channel_name=channel_name,
            platform=platform,
            stream_session_id=stream_session_id,
        )

        pending = self._get_pending_streak_chest(
            user_id=user_id,
            session_id=session_id,
            channel_name=channel_name,
            platform=platform,
            viewer_id=viewer_id,
        )
        if pending and normalized_source_event_id and pending.source_event_id == normalized_source_event_id:
            logger.info(
                "[DROPS] Duplicate pending streak event skipped for %s (%s)",
                viewer_name,
                normalized_source_event_id,
            )
            return None

        created = False
        upgraded = False
        now = utcnow_naive()
        if not pending:
            pending = PendingStreakChest(
                user_id=user_id,
                session_id=session_id,
                channel_name=channel_name,
                platform=platform,
                viewer_id=viewer_id,
                viewer_name=viewer_name,
                quality_id=quality.id,
                quality_name=quality_name,
                streak_days=streak.current_streak,
                messages_count=streak.messages_this_stream,
                source_event_id=normalized_source_event_id,
                chat_message_id=chat_message_id,
                stream_session_id=resolved_stream_session_id,
                status="pending",
                created_at=now,
                updated_at=now,
            )
            self.db.add(pending)
            created = True
        else:
            if self._quality_rank(quality_name) > self._quality_rank(pending.quality_name):
                pending.quality_id = quality.id
                pending.quality_name = quality_name
                upgraded = True
            pending.viewer_name = viewer_name
            pending.streak_days = max(pending.streak_days or 0, streak.current_streak)
            pending.messages_count = streak.messages_this_stream
            pending.source_event_id = normalized_source_event_id
            pending.chat_message_id = chat_message_id
            pending.stream_session_id = resolved_stream_session_id
            pending.updated_at = now

        self.db.commit()
        self.db.refresh(pending)

        return {
            "type": "streak_pending",
            "viewer_name": viewer_name,
            "quality": pending.quality_name,
            "pending_chest_id": pending.id,
            "created": created,
            "upgraded": upgraded,
            "streak_days": pending.streak_days,
            "stream_session_id": resolved_stream_session_id,
            "source_event_id": normalized_source_event_id,
        }

    def process_donation_drops(self, user_id: int = None, session_id: str = None, channel_name: str = None, platform: str = "twitch", viewer_id: str = None, viewer_name: str = None, donation_amount: float = None, source_event_id: str = None, donation_alert_id: str = None, stream_session_id: int = None) -> Optional[Dict[str, Any]]:
        """Process donation drops shared across platforms."""
        config = self.get_config(user_id=user_id, session_id=session_id, channel_name=channel_name, platform=None)
        if not config or not config.donation_enabled:
            return None

        normalized_source_event_id = self._normalize_source_event_id(
            source_event_id=source_event_id,
            donation_alert_id=donation_alert_id,
        )
        if normalized_source_event_id:
            existing_history = self._ensure_repo().get_history_by_source_event_id(
                source_event_id=normalized_source_event_id,
                channel_name=channel_name,
                platform=platform,
                user_id=user_id,
                session_id=session_id,
            )
            if existing_history:
                logger.info(
                    "[DROPS] Duplicate donation event skipped for %s (%s)",
                    viewer_name,
                    normalized_source_event_id,
                )
                return None

        quality_name = self._get_donation_quality(donation_amount, config)
        if not quality_name:
            return None

        quality = self.get_quality_by_name(quality_name)
        if not quality:
            return None

        reward = self._get_random_reward(user_id=user_id, session_id=session_id, channel_name=channel_name, platform=platform, quality_id=quality.id)
        if not reward:
            return None

        resolved_stream_session_id = self._resolve_stream_session_id(
            user_id=user_id,
            session_id=session_id,
            channel_name=channel_name,
            platform=platform,
            stream_session_id=stream_session_id,
            create_if_online=True,
        )
        history_entry = self._record_drops_history(
            user_id=user_id, session_id=session_id, channel_name=channel_name, platform=platform, viewer_id=viewer_id, viewer_name=viewer_name,
            drops_type="donation", quality_id=quality.id, reward=reward, donation_amount=donation_amount,
            stream_session_id=resolved_stream_session_id, source_event_id=normalized_source_event_id, donation_alert_id=donation_alert_id
        )
        if not history_entry:
            return None

        return {
            "type": "donation",
            "viewer_name": viewer_name,
            "quality": quality_name,
            "reward": reward.name,
            "reward_type": reward.reward_type,
            "reward_value": reward.reward_value,
            "donation_amount": donation_amount,
            "stream_session_id": resolved_stream_session_id,
            "source_event_id": normalized_source_event_id,
            "sound_file": reward.sound_file,
            "sound_volume": reward.sound_volume
        }

    def _get_streak_quality(self, days: int, config: DropsConfig) -> Optional[str]:
        """Resolve reward quality from streak length."""
        if days >= config.streak_days_legendary:
            return "Legendary"
        elif days >= config.streak_days_epic:
            return "Epic"
        elif days >= config.streak_days_rare:
            return "Rare"
        elif days >= config.streak_days_common:
            return "Common"
        return None

    def _get_donation_quality(self, amount: float, config: DropsConfig) -> Optional[str]:
        """Resolve reward quality from donation amount."""
        if amount >= config.donation_amount_legendary:
            return "Legendary"
        elif amount >= config.donation_amount_epic:
            return "Epic"
        elif amount >= config.donation_amount_rare:
            return "Rare"
        elif amount >= config.donation_amount_common:
            return "Common"
        return None

