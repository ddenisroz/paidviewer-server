# repositories/audio_settings_repository.py
"""
Repository for Audio Settings.
Follows Clean Architecture - abstracts all database access for AudioSettings.
"""
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from repositories.base_repository import BaseRepository
from models.tts import AudioSettings


class AudioSettingsRepository(BaseRepository[AudioSettings]):
    """Repository for AudioSettings CRUD operations."""
    
    def __init__(self, db: Session):
        super().__init__(AudioSettings, db)
    
    def get_by_user_id(self, user_id: int) -> Optional[AudioSettings]:
        """Get audio settings by user ID."""
        return self.db.query(AudioSettings).filter(
            AudioSettings.user_id == user_id
        ).first()
    
    def get_or_create(self, user_id: int) -> AudioSettings:
        """Get existing settings or create defaults."""
        settings = self.get_by_user_id(user_id)
        
        if not settings:
            settings = AudioSettings(
                user_id=user_id,
                website_volume=50,
                obs_volume=50
            )
            self.db.add(settings)
            self.db.commit()
            self.db.refresh(settings)
        
        return settings
    
    def update_volume(
        self,
        user_id: int,
        website_volume: Optional[int] = None,
        obs_volume: Optional[int] = None
    ) -> AudioSettings:
        """Update volume settings."""
        settings = self.get_or_create(user_id)
        
        if website_volume is not None:
            settings.website_volume = max(0, min(100, website_volume))
        if obs_volume is not None:
            settings.obs_volume = max(0, min(100, obs_volume))
        
        self.db.commit()
        self.db.refresh(settings)
        return settings
    
    def get_settings_dict(self, user_id: int) -> Dict[str, Any]:
        """Get audio settings as dictionary."""
        settings = self.get_or_create(user_id)
        return {
            "websiteVolume": settings.website_volume,
            "obsVolume": settings.obs_volume,
        }
