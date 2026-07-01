# features/drops/drops_config_service.py
"""Drops Config and Rewards management logic"""
import logging
import random
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from core.database import DropsConfig, DropsReward, DropsQuality, DropsHistory
from core.datetime_utils import utcnow_naive
from repositories.drops_history_repository import DropsHistoryRepository

logger = logging.getLogger(__name__)


class DropsConfigMixin:
    """Mixin for Drops Configuration and Rewards management"""

    # self.db must be available in the usage class
    db: Session

    def _get_config_repo(self):
        """Helper to get drops config repo"""
        from repositories.drops_config_repository import DropsConfigRepository
        return DropsConfigRepository(self.db)

    def _get_reward_repo(self):
        """Helper to get drops reward repo"""
        from repositories.drops_reward_repository import DropsRewardRepository
        return DropsRewardRepository(self.db)

    def _get_history_repo(self):
        """Helper to get drops history repo."""
        return DropsHistoryRepository(self.db)

    def _normalize_source_event_id(
        self,
        source_event_id: Optional[str] = None,
        donation_alert_id: Optional[str] = None,
        chat_message_id: Optional[int] = None,
    ) -> Optional[str]:
        """Build one stable idempotency key regardless of event source shape."""
        candidate = source_event_id
        if not candidate and donation_alert_id:
            candidate = f"donation_alert:{donation_alert_id}"
        elif candidate is None and chat_message_id is not None:
            candidate = f"chat_message:{chat_message_id}"

        if candidate is None:
            return None

        normalized = str(candidate).strip()
        return normalized or None

    def get_user_config(
        self,
        user_id: int,
        channel_name: str = None,
        platform: str = None,
    ) -> Optional[DropsConfig]:
        """Get the Drops configuration for an authenticated user."""
        target_platform = platform or "global"
        repo = self._get_config_repo()

        config = repo.get_by_user_channel_platform(
            user_id=user_id,
            channel_name=channel_name,
            platform=target_platform,
        )

        if not config and not platform:
            return self._create_global_config_from_user_configs(user_id, channel_name)

        return config

    def _create_global_config_from_user_configs(
        self,
        user_id: int,
        channel_name: str = None,
    ) -> Optional[DropsConfig]:
        """Build a global config from the user's existing Twitch/VK configs."""
        repo = self._get_config_repo()
        existing_configs = repo.get_existing_configs_for_user_compat(
            channel_name=channel_name,
            user_id=user_id,
        )

        if existing_configs:
            base_config = next((c for c in existing_configs if c.platform == "twitch"), existing_configs[0])

            streak_enabled_twitch = any(
                getattr(c, "streak_enabled_twitch", getattr(c, "streak_enabled", False))
                for c in existing_configs
                if c.platform == "twitch"
            )
            streak_enabled_vk = any(
                getattr(c, "streak_enabled_vk", getattr(c, "streak_enabled", False))
                for c in existing_configs
                if c.platform == "vk"
            )

            config = DropsConfig(
                user_id=user_id,
                channel_name=channel_name,
                platform="global",
                streak_days_common=base_config.streak_days_common,
                streak_days_rare=base_config.streak_days_rare,
                streak_days_epic=base_config.streak_days_epic,
                streak_days_legendary=base_config.streak_days_legendary,
                streak_messages_required=base_config.streak_messages_required,
                streak_reset_on_skip=getattr(base_config, "streak_reset_on_skip", True),
                streak_enabled_twitch=streak_enabled_twitch,
                streak_enabled_vk=streak_enabled_vk,
                donation_enabled=base_config.donation_enabled,
                donation_amount_common=base_config.donation_amount_common,
                donation_amount_rare=base_config.donation_amount_rare,
                donation_amount_epic=base_config.donation_amount_epic,
                donation_amount_legendary=base_config.donation_amount_legendary,
                mythical_enabled=base_config.mythical_enabled,
                mythical_min_interval_hours=base_config.mythical_min_interval_hours,
                mythical_max_interval_hours=base_config.mythical_max_interval_hours,
                mythical_window_duration_minutes=base_config.mythical_window_duration_minutes,
                mythical_donation_amount=base_config.mythical_donation_amount,
                widget_spinning_duration_ms=getattr(base_config, "widget_spinning_duration_ms", 5000),
                widget_opening_duration_ms=getattr(base_config, "widget_opening_duration_ms", 1000),
                widget_result_duration_ms=getattr(base_config, "widget_result_duration_ms", 5500),
                widget_closing_duration_ms=getattr(base_config, "widget_closing_duration_ms", 500),
                widget_spin_sound_file=getattr(base_config, "widget_spin_sound_file", None),
                widget_start_sound_file=getattr(base_config, "widget_start_sound_file", None),
                widget_reveal_sound_file=getattr(base_config, "widget_reveal_sound_file", None),
                widget_sound_volume=getattr(base_config, "widget_sound_volume", 1.0),
                widget_token=getattr(base_config, "widget_token", None),
            )
            self.db.add(config)
            self.db.commit()
            self.db.refresh(config)
            return config

        return None

    def create_or_update_user_config(
        self,
        user_id: int,
        channel_name: str = None,
        platform: str = None,
        config_data: Dict[str, Any] = None,
    ) -> DropsConfig:
        """Create or update the Drops configuration for an authenticated user."""
        target_platform = platform or "global"

        config = self.get_user_config(
            user_id=user_id,
            channel_name=channel_name,
            platform=target_platform,
        )

        if not config:
            config = DropsConfig(
                user_id=user_id,
                channel_name=channel_name,
                platform=target_platform,
            )
            self.db.add(config)

        if config_data:
            for field, value in config_data.items():
                if hasattr(config, field):
                    setattr(config, field, value)

        config.updated_at = utcnow_naive()

        try:
            self.db.commit()
            self.db.refresh(config)
        except Exception:
            logger.exception("[ERROR] Error saving drops config for %s", channel_name)
            self.db.rollback()
            raise

        return config

    def get_user_rewards(
        self,
        user_id: int,
        channel_name: str = None,
        platform: str = "twitch",
        quality_id: Optional[int] = None,
    ) -> List[DropsReward]:
        """Get active Drops rewards for the authenticated user's channel."""
        repo = self._get_reward_repo()
        return repo.get_active_by_user_and_channel(
            user_id=user_id,
            channel_name=channel_name,
            quality_id=quality_id,
        )

    def _get_random_user_reward(
        self,
        user_id: int,
        channel_name: str = None,
        platform: str = "twitch",
        quality_id: int = None,
    ) -> Optional[DropsReward]:
        """Get a random active reward for the authenticated user."""
        rewards = self.get_user_rewards(
            user_id=user_id,
            channel_name=channel_name,
            platform=platform,
            quality_id=quality_id,
        )
        if not rewards:
            logger.warning("No rewards found for quality_id=%s, channel=%s", quality_id, channel_name)
            return None

        total_weight = sum(reward.weight for reward in rewards)
        if total_weight == 0:
            logger.warning(
                "Total weight is 0 for rewards in channel %s, using uniform distribution",
                channel_name,
            )
            return random.choice(rewards)

        random_value = random.random() * total_weight
        current_weight = 0

        for reward in rewards:
            current_weight += reward.weight
            if random_value < current_weight:
                logger.debug(
                    "Selected reward '%s' (weight=%s/%s)",
                    reward.name,
                    reward.weight,
                    total_weight,
                )
                return reward

        logger.warning("Fallback to last reward for channel %s", channel_name)
        return rewards[-1]

    def get_config(self, user_id: int = None, session_id: str = None, channel_name: str = None, platform: str = None) -> Optional[DropsConfig]:
        """Get the Drops configuration for a channel
        
        When `platform` is not provided, returns the shared global config.
        """
        target_platform = platform or "global"

        target_platform = platform or "global"
        
        target_platform = platform or "global"

        from repositories.drops_config_repository import DropsConfigRepository
        repo = DropsConfigRepository(self.db)
        
        config = repo.get_by_filters(
            platform=target_platform,
            channel_name=channel_name,
            user_id=user_id,
            session_id=session_id
        )

        # When no platform is specified, try to synthesize a global config.
        if not config and not platform:
            return self._create_global_config_from_existing(user_id, session_id, channel_name)

        return config

    def _create_global_config_from_existing(self, user_id: int = None, session_id: str = None, channel_name: str = None) -> Optional[DropsConfig]:
        """Creates a global config from existing twitch/vk configs for backward compatibility"""
        """Creates a global config from existing twitch/vk configs for backward compatibility"""
        from repositories.drops_config_repository import DropsConfigRepository
        repo = DropsConfigRepository(self.db)
        
        existing_configs = repo.get_existing_configs_for_compat(
            channel_name=channel_name,
            user_id=user_id,
            session_id=session_id
        )

        if existing_configs:
            # Use first found config as base (twitch > vk)
            base_config = next((c for c in existing_configs if c.platform == 'twitch'), existing_configs[0])

            # Merge flags
            streak_enabled_twitch = any(
                getattr(c, 'streak_enabled_twitch', getattr(c, 'streak_enabled', False))
                for c in existing_configs if c.platform == 'twitch'
            )
            streak_enabled_vk = any(
                getattr(c, 'streak_enabled_vk', getattr(c, 'streak_enabled', False))
                for c in existing_configs if c.platform == 'vk'
            )

            config = DropsConfig(
                user_id=user_id,
                session_id=session_id,
                channel_name=channel_name,
                platform="global",
                streak_days_common=base_config.streak_days_common,
                streak_days_rare=base_config.streak_days_rare,
                streak_days_epic=base_config.streak_days_epic,
                streak_days_legendary=base_config.streak_days_legendary,
                streak_messages_required=base_config.streak_messages_required,
                streak_reset_on_skip=getattr(base_config, 'streak_reset_on_skip', True),
                streak_enabled_twitch=streak_enabled_twitch,
                streak_enabled_vk=streak_enabled_vk,
                donation_enabled=base_config.donation_enabled,
                donation_amount_common=base_config.donation_amount_common,
                donation_amount_rare=base_config.donation_amount_rare,
                donation_amount_epic=base_config.donation_amount_epic,
                donation_amount_legendary=base_config.donation_amount_legendary,
                mythical_enabled=base_config.mythical_enabled,
                mythical_min_interval_hours=base_config.mythical_min_interval_hours,
                mythical_max_interval_hours=base_config.mythical_max_interval_hours,
                mythical_window_duration_minutes=base_config.mythical_window_duration_minutes,
                mythical_donation_amount=base_config.mythical_donation_amount,
                widget_spinning_duration_ms=getattr(base_config, 'widget_spinning_duration_ms', 5000),
                widget_opening_duration_ms=getattr(base_config, 'widget_opening_duration_ms', 1000),
                widget_result_duration_ms=getattr(base_config, 'widget_result_duration_ms', 5500),
                widget_closing_duration_ms=getattr(base_config, 'widget_closing_duration_ms', 500),
                widget_spin_sound_file=getattr(base_config, 'widget_spin_sound_file', None),
                widget_start_sound_file=getattr(base_config, 'widget_start_sound_file', None),
                widget_reveal_sound_file=getattr(base_config, 'widget_reveal_sound_file', None),
                widget_sound_volume=getattr(base_config, 'widget_sound_volume', 1.0),
                widget_token=getattr(base_config, 'widget_token', None)
            )
            self.db.add(config)
            self.db.commit()
            self.db.refresh(config)
            return config
            
        return None

    def create_or_update_config(self, user_id: int = None, session_id: str = None, channel_name: str = None, platform: str = None, config_data: Dict[str, Any] = None) -> DropsConfig:
        """Create or update a Drops configuration."""
        target_platform = platform or "global"

        config = self.get_config(user_id=user_id, session_id=session_id, channel_name=channel_name, platform=target_platform)

        if not config:
            config = DropsConfig(
                user_id=user_id,
                session_id=session_id,
                channel_name=channel_name,
                platform=target_platform
            )
            self.db.add(config)

        if config_data:
            for field, value in config_data.items():
                if hasattr(config, field):
                    setattr(config, field, value)

        config.updated_at = utcnow_naive()

        try:
            self.db.commit()
            self.db.refresh(config)
        except Exception:
            logger.exception("[ERROR] Error saving drops config for {channel_name}")
            self.db.rollback()
            raise

        return config

    def get_rewards(self, user_id: int = None, session_id: str = None, channel_name: str = None, platform: str = "twitch", quality_id: Optional[int] = None) -> List[DropsReward]:
        """Get channel rewards shared across all platforms."""
        from repositories.drops_reward_repository import DropsRewardRepository
        repo = DropsRewardRepository(self.db)
        
        return repo.get_by_filters(
            channel_name=channel_name,
            user_id=user_id,
            session_id=session_id,
            quality_id=quality_id,
            is_active=True
        )

    def get_quality_by_name(self, quality_name: str) -> Optional[DropsQuality]:
        """Get a quality record by name."""
        """Get a quality record by name."""
        from repositories.drops_reward_repository import DropsRewardRepository
        return DropsRewardRepository(self.db).get_quality_by_name(quality_name)

    def _get_random_reward(self, user_id: int = None, session_id: str = None, channel_name: str = None, platform: str = "twitch", quality_id: int = None) -> Optional[DropsReward]:
        """Pick a weighted random reward for the requested quality."""
        rewards = self.get_rewards(user_id=user_id, session_id=session_id, channel_name=channel_name, platform=platform, quality_id=quality_id)
        if not rewards:
            logger.warning(f"No rewards found for quality_id={quality_id}, channel={channel_name}")
            return None

        total_weight = sum(reward.weight for reward in rewards)
        if total_weight == 0:
            logger.warning(f"Total weight is 0 for rewards in channel {channel_name}, using uniform distribution")
            return random.choice(rewards)

        random_value = random.random() * total_weight
        current_weight = 0

        for reward in rewards:
            current_weight += reward.weight
            if random_value < current_weight:
                logger.debug(f"Selected reward '{reward.name}' (weight={reward.weight}/{total_weight})")
                return reward

        logger.warning(f"Fallback to last reward for channel {channel_name}")
        return rewards[-1]

    def _record_drops_history(self, user_id: int = None, session_id: str = None, channel_name: str = None, platform: str = "twitch", viewer_id: str = None, viewer_name: str = None, drops_type: str = None, quality_id: int = None, reward: DropsReward = None, **kwargs):
        """Write a Drops event to history."""
        history_kwargs = dict(kwargs)
        history_repo = self._get_history_repo()
        source_event_id = self._normalize_source_event_id(
            source_event_id=history_kwargs.pop("source_event_id", None),
            donation_alert_id=history_kwargs.get("donation_alert_id"),
            chat_message_id=history_kwargs.get("chat_message_id"),
        )
        history_entry, _ = history_repo.get_or_create_history_entry(
            user_id=user_id,
            session_id=session_id,
            channel_name=channel_name,
            platform=platform,
            viewer_id=viewer_id,
            viewer_name=viewer_name,
            lootbox_type=drops_type,
            quality_id=quality_id,
            reward_id=reward.id if reward else None,
            reward_name=reward.name if reward else "",
            reward_type=reward.reward_type if reward else "",
            reward_value=reward.reward_value if reward else "",
            source_event_id=source_event_id,
            **history_kwargs,
        )
        return history_entry

