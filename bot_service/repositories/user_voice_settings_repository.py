# repositories/user_voice_settings_repository.py
"""
Repository for User Voice Settings.
Follows Clean Architecture - abstracts all database access for UserVoiceSettings.
"""
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from repositories.base_repository import BaseRepository
from models.tts import UserVoiceSettings


class UserVoiceSettingsRepository(BaseRepository[UserVoiceSettings]):
    """Repository for UserVoiceSettings CRUD operations."""
    
    def __init__(self, db: Session):
        super().__init__(UserVoiceSettings, db)
    
    def get_by_user_id(self, user_id: int, tts_provider: str = "f5") -> List[UserVoiceSettings]:
        """Get all voice settings for a user."""
        return self.db.query(UserVoiceSettings).filter(
            UserVoiceSettings.user_id == user_id,
            UserVoiceSettings.tts_provider == tts_provider,
        ).all()
    
    def get_by_voice_name(
        self,
        user_id: int,
        voice_name: str,
        tts_provider: str = "f5",
    ) -> Optional[UserVoiceSettings]:
        """Get voice settings for a specific voice."""
        return self.db.query(UserVoiceSettings).filter(
            UserVoiceSettings.user_id == user_id,
            UserVoiceSettings.voice_name == voice_name,
            UserVoiceSettings.tts_provider == tts_provider,
        ).first()
    
    def get_or_create(
        self,
        user_id: int,
        voice_name: str,
        tts_provider: str = "f5",
    ) -> UserVoiceSettings:
        """Get existing voice settings or create defaults."""
        settings = self.get_by_voice_name(user_id, voice_name, tts_provider=tts_provider)
        
        if not settings:
            settings = UserVoiceSettings(
                user_id=user_id,
                voice_name=voice_name,
                tts_provider=tts_provider,
            )
            self.db.add(settings)
            self.db.commit()
            self.db.refresh(settings)
        
        return settings
    
    def update_settings(
        self,
        user_id: int,
        voice_name: str,
        cfg_strength: Optional[float] = None,
        speed_preset: Optional[str] = None,
        volume: Optional[int] = None,
        tts_provider: str = "f5",
    ) -> UserVoiceSettings:
        """Update voice settings."""
        settings = self.get_or_create(user_id, voice_name, tts_provider=tts_provider)
        
        if cfg_strength is not None:
            settings.cfg_strength = cfg_strength
        if speed_preset is not None:
            settings.speed_preset = speed_preset
        if volume is not None:
            settings.volume = max(0, min(100, volume))
        
        self.db.commit()
        self.db.refresh(settings)
        return settings
    
    def get_settings_dict(
        self,
        user_id: int,
        voice_name: str,
        tts_provider: str = "f5",
    ) -> Optional[Dict[str, Any]]:
        """Get voice settings as dictionary."""
        settings = self.get_by_voice_name(user_id, voice_name, tts_provider=tts_provider)
        if not settings:
            return None
        
        return {
            "voice_name": settings.voice_name,
            "tts_provider": settings.tts_provider,
            "cfg_strength": settings.cfg_strength,
            "speed_preset": settings.speed_preset,
            "volume": settings.volume,
        }

    def get_by_user_and_voice_id(
        self,
        user_id: int,
        voice_id: int,
        tts_provider: str = "f5",
    ) -> Optional[UserVoiceSettings]:
        """Get voice settings for a specific user and voice ID."""
        return self.db.query(UserVoiceSettings).filter(
            UserVoiceSettings.user_id == user_id,
            UserVoiceSettings.voice_id == voice_id,
            UserVoiceSettings.tts_provider == tts_provider,
        ).first()

    def delete_by_voice_id(self, voice_id: int, tts_provider: Optional[str] = None) -> int:
        """Delete all settings for a voice ID. Returns count deleted."""
        query = self.db.query(UserVoiceSettings).filter(UserVoiceSettings.voice_id == voice_id)
        if tts_provider:
            query = query.filter(UserVoiceSettings.tts_provider == tts_provider)
        result = query.delete()
        self.db.commit()
        return result
    
    def update_or_create_by_voice_id(
        self,
        user_id: int,
        voice_id: int,
        settings_data: Dict[str, Any],
        tts_provider: str = "f5",
    ) -> UserVoiceSettings:
        """Update existing or create new settings by voice_id."""
        from core.datetime_utils import utcnow_naive
        
        settings = self.get_by_user_and_voice_id(user_id, voice_id, tts_provider=tts_provider)
        
        if settings:
            if 'cfg_strength' in settings_data:
                settings.cfg_strength = settings_data['cfg_strength']
            if 'speed_preset' in settings_data:
                settings.speed_preset = settings_data['speed_preset']
            if 'volume' in settings_data:
                settings.volume = max(0, min(100, int(settings_data['volume'])))
            settings.updated_at = utcnow_naive()
        else:
            settings = UserVoiceSettings(
                user_id=user_id,
                voice_id=voice_id,
                voice_name=settings_data.get('voice_name'),
                tts_provider=tts_provider,
                cfg_strength=settings_data.get('cfg_strength'),
                speed_preset=settings_data.get('speed_preset'),
                volume=max(0, min(100, int(settings_data['volume'])))
                if settings_data.get('volume') is not None
                else None,
            )
            self.db.add(settings)
        
        self.db.commit()
        self.db.refresh(settings)
        return settings


