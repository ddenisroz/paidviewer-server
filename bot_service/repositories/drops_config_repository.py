# bot_service/repositories/drops_config_repository.py
from typing import Optional, List, Dict
from sqlalchemy.orm import Session
from sqlalchemy import func

from repositories.base_repository import BaseRepository
from models.drops import DropsConfig, DropsQuality

class DropsConfigRepository(BaseRepository[DropsConfig]):
    """
    Repository for DropsConfig and DropsQuality entities.
    """
    def __init__(self, db: Session):
        super().__init__(DropsConfig, db)

    # === DropsConfig ===

    def get_by_user(self, user_id: int) -> Optional[DropsConfig]:
        """Get drops config by user ID."""
        return self.db.query(DropsConfig).filter(DropsConfig.user_id == user_id).first()

    def get_by_user_channel_platform(
        self,
        user_id: int,
        channel_name: Optional[str] = None,
        platform: str = "global",
    ) -> Optional[DropsConfig]:
        """Get config for an authenticated user by channel and platform."""
        query = self.db.query(DropsConfig).filter(
            DropsConfig.user_id == user_id,
            DropsConfig.platform == platform,
        )

        if channel_name:
            query = query.filter(DropsConfig.channel_name == channel_name)

        return query.first()
    
    def get_by_widget_token(self, token: str) -> Optional[DropsConfig]:
        """Get drops config by widget token."""
        return self.db.query(DropsConfig).filter(DropsConfig.widget_token == token).first()

    def get_by_filters(
        self,
        platform: str,
        channel_name: Optional[str] = None,
        user_id: Optional[int] = None,
        session_id: Optional[str] = None
    ) -> Optional[DropsConfig]:
        """Get config by platform and one of channel/user/session."""
        query = self.db.query(DropsConfig).filter(DropsConfig.platform == platform)
        
        if channel_name:
            query = query.filter(DropsConfig.channel_name == channel_name)
        
        if user_id:
            query = query.filter(DropsConfig.user_id == user_id)
        elif session_id:
            query = query.filter(DropsConfig.session_id == session_id)
            
        return query.first()

    def get_existing_configs_for_compat(
        self, 
        channel_name: str, 
        user_id: Optional[int] = None, 
        session_id: Optional[str] = None
    ) -> List[DropsConfig]:
        """Get existing Twitch/VK configs for migration/global config creation."""
        query = self.db.query(DropsConfig).filter(DropsConfig.channel_name == channel_name)
        
        if user_id:
            query = query.filter(DropsConfig.user_id == user_id)
        elif session_id:
            query = query.filter(DropsConfig.session_id == session_id)
            
        return query.filter(DropsConfig.platform.in_(['twitch', 'vk'])).all()

    def get_existing_configs_for_user_compat(
        self,
        channel_name: str,
        user_id: int,
    ) -> List[DropsConfig]:
        """Get existing Twitch/VK configs for a user during global-config migration."""
        return (
            self.db.query(DropsConfig)
            .filter(
                DropsConfig.channel_name == channel_name,
                DropsConfig.user_id == user_id,
                DropsConfig.platform.in_(["twitch", "vk"]),
            )
            .all()
        )

    # === DropsQuality ===

    def get_all_qualities(self) -> List[DropsQuality]:
        """Get all drop qualities."""
        return self.db.query(DropsQuality).all()

    def get_quality_by_name(self, name: str) -> Optional[DropsQuality]:
        """Get quality by name."""
        normalized_name = (name or "").strip().lower()
        return self.db.query(DropsQuality).filter(func.lower(DropsQuality.name) == normalized_name).first()
    
    def get_qualities_by_ids(self, ids: List[int]) -> List[DropsQuality]:
        """Get qualities by IDs."""
        if not ids:
             return []
        return self.db.query(DropsQuality).filter(DropsQuality.id.in_(ids)).all()
