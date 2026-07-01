# repositories/tts_settings_repository.py
"""
Repository for TTS User Settings.
Follows Clean Architecture - abstracts all database access for TTSUserSettings.
"""
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from repositories.base_repository import BaseRepository
from models.tts import TTSUserSettings
from services.tts.provider_utils import (
    infer_provider_from_engine,
    normalize_provider_mode,
)


class TTSSettingsRepository(BaseRepository[TTSUserSettings]):
    """Repository for TTSUserSettings CRUD operations."""
    
    def __init__(self, db: Session):
        super().__init__(TTSUserSettings, db)
    
    def get_by_user_id(self, user_id: int) -> Optional[TTSUserSettings]:
        """Get TTS settings by user ID."""
        return self.db.query(TTSUserSettings).filter(
            TTSUserSettings.user_id == user_id
        ).first()
    
    def get_or_create(self, user_id: int) -> TTSUserSettings:
        """Get existing settings or create defaults for an authenticated user."""
        if not user_id:
            raise ValueError("user_id is required")

        settings = self.get_by_user_id(user_id)
        
        if not settings:
            settings = TTSUserSettings(user_id=user_id)
            self.db.add(settings)
            self.db.commit()
            self.db.refresh(settings)
        
        return settings
    
    def update_settings(
        self,
        settings: TTSUserSettings,
        data: Dict[str, Any]
    ) -> TTSUserSettings:
        """Update TTS settings with provided data."""
        for key, value in data.items():
            if hasattr(settings, key):
                setattr(settings, key, value)
        
        self.db.commit()
        self.db.refresh(settings)
        return settings
    
    def get_settings_dict(self, settings: TTSUserSettings) -> Dict[str, Any]:
        """Convert settings to dictionary for API response."""
        provider = infer_provider_from_engine(
            settings.engine,
            advanced_provider=getattr(settings, "advanced_provider", None),
        )
        if provider == "f5":
            use_local_tts = normalize_provider_mode(getattr(settings, "f5_mode", "cloud")) == "local"
        else:
            use_local_tts = False

        return {
            "enable_7tv": settings.enable_7tv,
            "enable_twitch": settings.enable_twitch,
            "enable_lexicon_filter": settings.enable_lexicon_filter,
            "enable_custom_lexicon": settings.enable_custom_lexicon,
            "engine": settings.engine,
            "voice": settings.voice,
            "listening_mode": settings.listening_mode,
            "advanced_provider": getattr(settings, "advanced_provider", "f5") or "f5",
            "f5_mode": getattr(settings, "f5_mode", "cloud") or "cloud",
            "gcloud_voices": settings.gcloud_voices or [],
            "gcloud_mood": settings.gcloud_mood or "neutral",
            "max_message_length": settings.max_message_length,
            "skip_commands": settings.skip_commands,
            "use_local_tts": use_local_tts,
            "filter_replies": settings.filter_replies,
            "filter_mentions": settings.filter_mentions,
            "direct_interactions_enabled": not settings.filter_replies and not settings.filter_mentions,
            "filter_banwords": getattr(settings, "filter_banwords", True),
            "disable_voice_selection": getattr(settings, "disable_voice_selection", False),
            "speak_sender_name": getattr(settings, "speak_sender_name", False),
            "tts_mode": settings.tts_mode,
            "tts_reward_ids": settings.tts_reward_ids or {},
            "enabled_platforms": settings.enabled_platforms or [],
        }
    
    def delete_by_user_id(self, user_id: int) -> int:
        """Delete settings by user ID."""
        result = self.db.query(TTSUserSettings).filter(
            TTSUserSettings.user_id == user_id
        ).delete()
        self.db.commit()
        return result
