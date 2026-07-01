# bot_service/repositories/chatbox_repository.py
"""
Repository for ChatBoxSettings entities.
Clean Architecture: abstracts DB access for chat box settings.
"""

import logging
import secrets
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from repositories.base_repository import BaseRepository
from core.database import ChatBoxSettings, User

logger = logging.getLogger(__name__)


def generate_widget_token() -> str:
    """Generate a unique widget token (32 characters)."""
    return secrets.token_urlsafe(24)


class ChatBoxRepository(BaseRepository[ChatBoxSettings]):
    """Repository for ChatBoxSettings entity."""
    
    def __init__(self, db: Session):
        super().__init__(ChatBoxSettings, db)
    
    def get_by_user_id(self, user_id: int) -> Optional[ChatBoxSettings]:
        """Get settings for a specific user."""
        return self.db.query(ChatBoxSettings).filter(
            ChatBoxSettings.user_id == user_id
        ).first()
    
    def get_by_token(self, token: str) -> Optional[ChatBoxSettings]:
        """Get settings by widget token (for OBS widget)."""
        return self.db.query(ChatBoxSettings).filter(
            ChatBoxSettings.widget_token == token
        ).first()
    
    def get_or_create(self, user_id: int) -> ChatBoxSettings:
        """Get existing settings or create new default settings."""
        settings = self.get_by_user_id(user_id)
        if not settings:
            settings = ChatBoxSettings(
                user_id=user_id,
                widget_token=generate_widget_token()
            )
            self.db.add(settings)
            self.db.commit()
            self.db.refresh(settings)
            logger.info(f"[CHATBOX] Created default settings for user {user_id}")
        return settings
    
    def update_settings(
        self,
        user_id: int,
        settings_data: Dict[str, Any],
        client_version: Optional[int] = None,
        regenerate_token: bool = False
    ) -> ChatBoxSettings:
        """Update settings with version check and optional token regeneration.
        
        Raises:
            ValueError: If version conflict detected
        """
        settings = self.get_or_create(user_id)
        
        # Version conflict check
        if client_version is not None and hasattr(settings, 'version'):
            if settings.version != client_version:
                raise ValueError(f"Version conflict: DB version={settings.version}, client version={client_version}")
        
        # Update settings (exclude version from update)
        for key, value in settings_data.items():
            if key != 'version' and hasattr(settings, key):
                setattr(settings, key, value)
        
        # Increment version
        if hasattr(settings, 'version'):
            settings.version += 1
        
        # Token regeneration
        if regenerate_token:
            old_token = settings.widget_token
            settings.widget_token = generate_widget_token()
            logger.info(f"[CHATBOX] Token regenerated for user {user_id}: {old_token[:8]}... -> {settings.widget_token[:8]}...")
        
        self.db.commit()
        self.db.refresh(settings)
        return settings
    
    def get_user_channel_name(self, user_id: int) -> Optional[str]:
        """Get the Twitch username for a user."""
        user = self.db.query(User).filter(User.id == user_id).first()
        return user.twitch_username if user else None

    def delete_by_user_id(self, user_id: int) -> int:
        """Delete settings for a user."""
        return self.db.query(ChatBoxSettings).filter(
            ChatBoxSettings.user_id == user_id
        ).delete()
