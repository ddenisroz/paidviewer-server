# features/drops/drops_mythical_service.py
"""Drops Mythical session management and event processing"""
import logging
import random
from datetime import timedelta
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from core.database import MythicalDropsSession, DropsConfig
from core.datetime_utils import utcnow_naive

from repositories.drops_history_repository import DropsHistoryRepository
from repositories.user_token_repository import UserTokenRepository
from repositories.drops_config_repository import DropsConfigRepository

logger = logging.getLogger(__name__)


class DropsMythicalMixin:
    """Mixin for Mythical Drops management
    
    Requires DropsConfigMixin for config methods.
    Assumes self.db is available.
    """

    # self.db must be available in the usage class
    db: Session
    
    # Optional repositories
    history_repo: Optional[DropsHistoryRepository] = None
    config_repo: Optional[DropsConfigRepository] = None

    # Expected methods from DropsConfigMixin
    def get_config(self, **kwargs): pass
    def get_quality_by_name(self, name): pass
    def _get_random_reward(self, **kwargs): pass
    def _record_drops_history(self, **kwargs): pass

    def _ensure_mythical_repos(self):
        if not getattr(self, 'history_repo', None):
             self.history_repo = DropsHistoryRepository(self.db)
        if not getattr(self, 'token_repo', None):
             self.token_repo = UserTokenRepository(self.db)
        # config_repo might be present or not
        return self.history_repo, self.token_repo

    def process_mythical_drops_for_user(
        self,
        user_id: int,
        channel_name: str = None,
        platform: str = "twitch",
        viewer_id: str = None,
        viewer_name: str = None,
    ) -> Optional[Dict[str, Any]]:
        """Active user-only wrapper for mythical drops processing."""
        return self.process_mythical_drops(
            user_id=user_id,
            session_id=None,
            channel_name=channel_name,
            platform=platform,
            viewer_id=viewer_id,
            viewer_name=viewer_name,
        )

    def check_mythical_drops_for_user(
        self,
        user_id: int,
        channel_name: str = None,
        platform: str = "twitch",
    ) -> bool:
        """Active user-only wrapper for mythical readiness checks."""
        return self.check_mythical_drops(
            user_id=user_id,
            session_id=None,
            channel_name=channel_name,
            platform=platform,
        )

    def start_mythical_drops_for_user(
        self,
        user_id: int,
        channel_name: str = None,
        platform: str = "twitch",
    ) -> Optional[MythicalDropsSession]:
        """Active user-only wrapper for mythical session start."""
        return self.start_mythical_drops(
            user_id=user_id,
            session_id=None,
            channel_name=channel_name,
            platform=platform,
        )

    def process_mythical_drops_with_active_user_session(
        self,
        user_id: int,
        channel_name: str = None,
        platform: str = "twitch",
        viewer_id: str = None,
        viewer_name: str = None,
        amount: float = None,
    ) -> Optional[Dict[str, Any]]:
        """Active user-only wrapper for mythical donation window processing."""
        return self.process_mythical_drops_with_session(
            user_id=user_id,
            session_id=None,
            channel_name=channel_name,
            platform=platform,
            viewer_id=viewer_id,
            viewer_name=viewer_name,
            amount=amount,
        )

    def process_mythical_drops(self, user_id: int = None, session_id: str = None, channel_name: str = None, platform: str = "twitch", viewer_id: str = None, viewer_name: str = None) -> Optional[Dict[str, Any]]:
        """Process mythical drops."""
        config = self.get_config(user_id=user_id, session_id=session_id, channel_name=channel_name, platform=None)
        if not config or not config.mythical_enabled:
            return None

        if not self._can_activate_mythical(config):
            return None

        quality = self.get_quality_by_name("Mythical")
        if not quality:
            return None

        reward = self._get_random_reward(user_id=user_id, session_id=session_id, channel_name=channel_name, platform=platform, quality_id=quality.id)
        if not reward:
            return None

        config.mythical_last_appeared = utcnow_naive()
        # Ensure persistence (using self.db commit or repo save if available)
        self.db.commit() # Config usually attached to session

        self._record_drops_history(
            user_id=user_id, session_id=session_id, channel_name=channel_name, platform=platform, viewer_id=viewer_id, viewer_name=viewer_name,
            drops_type="mythical", quality_id=quality.id, reward=reward
        )

        return {
            "type": "mythical",
            "viewer_name": viewer_name,
            "quality": "Mythical",
            "reward": reward.name,
            "reward_type": reward.reward_type,
            "reward_value": reward.reward_value,
            "sound_file": reward.sound_file,
            "sound_volume": reward.sound_volume
        }

    def _can_activate_mythical(self, config: DropsConfig) -> bool:
        """Check whether the mythical lootbox can be activated."""
        if not config.mythical_last_appeared:
            return True

        now = utcnow_naive()
        time_since_last = (now - config.mythical_last_appeared).total_seconds() / 3600  # in hours

        return time_since_last >= config.mythical_min_interval_hours

    def check_mythical_drops(self, user_id: int = None, session_id: str = None, channel_name: str = None, platform: str = "twitch") -> bool:
        """Check whether mythical drops can be started."""
        config = self.get_config(user_id=user_id, session_id=session_id, channel_name=channel_name, platform=platform)
        if not config or not config.mythical_enabled:
            return False

        hist_repo, token_repo = self._ensure_mythical_repos()
        
        # Check DonationAlerts token
        da_token = None
        if user_id:
            da_token = token_repo.get_active_token(user_id, 'donationalerts')
        elif session_id:
             # Fallback for session-based lookup
             da_token = token_repo.get_active_token_by_session(session_id, 'donationalerts')

        if not da_token:
            logger.debug(f"[BLOCKED] [MYTHICAL] DonationAlerts not connected, cannot activate mythical drops for {channel_name}")
            return False

        is_stream_online = self._check_stream_online(user_id=user_id, session_id=session_id, channel_name=channel_name, platform=platform)
        if not is_stream_online:
            logger.debug(f"[BLOCKED] [MYTHICAL] Stream is offline, cannot activate mythical drops for {channel_name}")
            return False

        if config.mythical_last_appeared:
            time_since_last = utcnow_naive() - config.mythical_last_appeared
            min_interval = timedelta(hours=config.mythical_min_interval_hours)
            if time_since_last < min_interval:
                return False

            max_interval = timedelta(hours=config.mythical_max_interval_hours)
            if time_since_last > max_interval:
                return True
        else:
            return True

        return random.random() < 0.1

    def _check_stream_online(self, user_id: int = None, session_id: str = None, channel_name: str = None, platform: str = "twitch") -> bool:
        """Check whether the stream is online on the requested platform."""
        try:
            from core.database import User, UserToken # Needed for type checking or fallbacks?
            from core.connection_manager import get_connection_manager
            
            # Use Repos
            hist_repo, token_repo = self._ensure_mythical_repos()
            # We need UserRepository too?
            from repositories.user_repository import UserRepository
            user_repo = UserRepository(self.db)

            connection_manager = get_connection_manager()
            if connection_manager.is_channel_active(channel_name):
                return True

            if user_id:
                user = user_repo.get(user_id)
                if not user:
                    return False

                if platform == "twitch" and user.twitch_username:
                    return connection_manager.is_channel_active(user.twitch_username.lower())
                elif platform == "vk":
                    vk_token = token_repo.get_active_token(user_id, 'vk')
                    if vk_token and user.vk_channel_name:
                        return connection_manager.is_channel_active(user.vk_channel_name)

            return False
        except Exception:
            logger.exception("Error checking stream online status")
            return False

    def start_mythical_drops(self, user_id: int = None, session_id: str = None, channel_name: str = None, platform: str = "twitch") -> Optional[MythicalDropsSession]:
        """Start a mythical drops window."""
        config = self.get_config(user_id=user_id, session_id=session_id, channel_name=channel_name, platform=platform)
        if not config or not config.mythical_enabled:
            return None

        # Re-check da_token using repo
        hist_repo, token_repo = self._ensure_mythical_repos()
        
        da_token = None
        if user_id:
            da_token = token_repo.get_active_token(user_id, 'donationalerts')
        elif session_id:
             da_token = token_repo.get_active_token_by_session(session_id, 'donationalerts')

        if not da_token:
            logger.warning(f"[BLOCKED] [MYTHICAL] Cannot activate mythical drops: DonationAlerts not connected for {channel_name}")
            return None

        is_stream_online = self._check_stream_online(user_id=user_id, session_id=session_id, channel_name=channel_name, platform=platform)
        if not is_stream_online:
            logger.warning(f"[BLOCKED] [MYTHICAL] Cannot activate mythical drops: stream is offline for {channel_name}")
            return None

        now = utcnow_naive()
        expires_at = now + timedelta(minutes=config.mythical_window_duration_minutes)

        session = MythicalDropsSession(
            user_id=user_id,
            session_id=session_id,
            channel_name=channel_name,
            platform=platform,
            donation_amount=config.mythical_donation_amount,
            window_duration_minutes=config.mythical_window_duration_minutes,
            expires_at=expires_at
        )

        # Use repo to add
        hist_repo.add_mythical_session(session)

        config.mythical_last_appeared = now
        config.updated_at = now

        try:
            self.db.commit() # config update
        except Exception:
            logger.exception("[ERROR] Error starting mythical drops for {channel_name}")
            self.db.rollback()
            return None

        return session

    def process_mythical_drops_with_session(self, user_id: int = None, session_id: str = None, channel_name: str = None, platform: str = "twitch", viewer_id: str = None, viewer_name: str = None, amount: float = None) -> Optional[Dict[str, Any]]:
        """Process mythical drops for an active mythical session."""
        hist_repo, token_repo = self._ensure_mythical_repos()
        
        # Use simple get_active_mythical_session logic from repo
        # Repo expects explicit params.
        now = utcnow_naive()
        session = hist_repo.get_active_mythical_session(channel_name, now, user_id, session_id)
        # Note: repo method checks platform? 
        # My repo method: filter(channel_name). is_active=True. expires_at > now. 
        # Does NOT filter by platform in repo implementation?
        # Original code filtered by platform: MythicalDropsSession.platform == platform
        # I should probably update repo to filter by platform if needed.
        # Or check platform here.
        
        if not session:
            return None
        
        if session.platform != platform:
            return None # Mismatch

        if amount < session.donation_amount:
            return None

        quality = self.get_quality_by_name("Legendary")
        if not quality:
            return None

        reward = self._get_random_reward(user_id=user_id, session_id=session_id, channel_name=channel_name, platform=platform, quality_id=quality.id)
        if not reward:
            return None

        self._record_drops_history(
            user_id=user_id, session_id=session_id, channel_name=channel_name, platform=platform, viewer_id=viewer_id, viewer_name=viewer_name,
            drops_type="mythical", quality_id=quality.id, reward=reward, donation_amount=amount
        )

        session.is_active = False
        session.winner_viewer_id = viewer_id
        session.winner_viewer_name = viewer_name
        session.winner_donation_amount = amount

        hist_repo.update_mythical_session(session)

        return {
            "type": "mythical",
            "viewer_name": viewer_name,
            "quality": "Legendary",
            "reward": reward.name,
            "reward_type": reward.reward_type,
            "reward_value": reward.reward_value,
            "sound_file": reward.sound_file,
            "sound_volume": reward.sound_volume,
            "donation_amount": amount
        }

