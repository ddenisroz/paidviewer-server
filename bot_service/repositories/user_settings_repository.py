# bot_service/repositories/user_settings_repository.py
"""Repository for authenticated user settings."""
from typing import Optional, Dict, Any, List
from sqlalchemy import func
from sqlalchemy.orm import Session

from models.user import User, UserSettings
from repositories.base_repository import BaseRepository


class UserSettingsRepository(BaseRepository[UserSettings]):
    """
    Repository for UserSettings entities.
    """
    
    def __init__(self, db: Session):
        super().__init__(UserSettings, db)

    def get_by_filters(self, filters: Dict[str, Any]) -> Optional[UserSettings]:
        """
        Get settings by generic filters.
        Used for authenticated user lookups and channel-scoped discovery.
        """
        return self.db.query(UserSettings).filter_by(**filters).first()

    def get_by_user_id(self, user_id: int) -> Optional[UserSettings]:
        """Get settings by user ID."""
        return self.db.query(UserSettings).filter(UserSettings.user_id == user_id).first()

    def get_by_channel_name(self, channel_name: str) -> Optional[UserSettings]:
        """
        Get settings by Twitch channel name.
        First tries user_settings.channel_name, then falls back to users.twitch_username.
        """
        normalized = (channel_name or "").strip().lower()
        if not normalized:
            return None

        by_settings_channel = self.db.query(UserSettings).filter(
            func.lower(UserSettings.channel_name) == normalized
        ).first()
        if by_settings_channel:
            return by_settings_channel

        return self.db.query(UserSettings).join(
            User, User.id == UserSettings.user_id
        ).filter(
            func.lower(User.twitch_username) == normalized
        ).first()

    def create_default(self, user_data: Dict[str, Any]) -> UserSettings:
        """Create default settings for an authenticated user."""
        settings = UserSettings(**user_data)
        self.db.add(settings)
        self.db.commit()
        self.db.refresh(settings)
        return settings
    
    def get_with_chat_enabled(self) -> List[UserSettings]:
        """Get all settings where chat is enabled."""
        return self.db.query(UserSettings).filter(
            UserSettings.chat_enabled.is_(True)
        ).all()

    def delete_by_user_id(self, user_id: int) -> int:
        """Delete settings for a user."""
        return self.db.query(UserSettings).filter(
            UserSettings.user_id == user_id
        ).delete()

