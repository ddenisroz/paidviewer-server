from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from repositories.base_repository import BaseRepository
from models.user import User
from core.database import UserToken


class UserRepository(BaseRepository[User]):
    """
    Repository for User entity.
    """
    def __init__(self, db: Session):
        super().__init__(User, db)

    def get_by_id(self, user_id: int) -> Optional[User]:
        """Get user by ID."""
        return self.db.query(User).filter(User.id == user_id).first()

    def update(self, user: User, data: Dict[str, Any]) -> User:
        """Update user with provided data and commit."""
        for key, value in data.items():
            if hasattr(user, key):
                setattr(user, key, value)
        self.db.commit()
        self.db.refresh(user)
        return user

    def get_by_twitch_username(self, username: str) -> Optional[User]:
        """Get user by Twitch username (case-insensitive)."""
        return self.db.query(User).filter(User.twitch_username.ilike(username)).first()

    def get_by_vk_channel_name(self, channel_name: str) -> Optional[User]:
        """Get user by VK channel name (case-insensitive)."""
        return self.db.query(User).filter(User.vk_channel_name.ilike(channel_name)).first()

    def get_by_vk_username(self, username: str) -> Optional[User]:
        """Get user by VK username (case-insensitive)."""
        return self.db.query(User).filter(User.vk_username.ilike(username)).first()

    def count_all(self) -> int:
        """Count total users."""
        return self.db.query(User).count()

    def count_active(self) -> int:
        """Count active users."""
        return self.db.query(User).filter(User.is_active == True).count()

    def get_all_active(self) -> List[User]:
        """Get all active users."""
        return self.db.query(User).filter(User.is_active == True).all()
    
    def is_username_taken(self, username: str) -> bool:
        """Check if username is already taken (case-insensitive)."""
        from sqlalchemy import or_
        return self.db.query(User).filter(
            or_(
                User.twitch_username.ilike(username),
                User.vk_username.ilike(username)
            )
        ).first() is not None
    
    def get_user_tokens(self, user_id: int) -> List[UserToken]:
        """Get all tokens for a user."""
        return self.db.query(UserToken).filter(UserToken.user_id == user_id).all()
    
    def get_active_with_twitch_token(self) -> List[User]:
        """Get active users with Twitch token."""
        return self.db.query(User).filter(
            User.twitch_access_token.isnot(None),
            User.is_active == True
        ).all()
    
    def get_active_with_vk_token(self) -> List[User]:
        """Get active users with VK token."""
        return self.db.query(User).filter(
            User.vk_access_token.isnot(None),
            User.is_active == True
        ).all()
    
    def get_token_by_platform(self, platform: str, platform_user_id: str) -> Optional[UserToken]:
        """Get UserToken by platform and platform_user_id."""
        return self.db.query(UserToken).filter(
            UserToken.platform == platform,
            UserToken.platform_user_id == str(platform_user_id)
        ).first()

    def update_obs_token(self, user_id: int, obs_token: str) -> Optional[User]:
        """Update or create user with OBS token."""
        user = self.get_by_id(user_id)
        if user:
            user.obs_token = obs_token
            self.db.commit()
            return user
        return None

    def update_tts_obs_token(self, user_id: int, field_name: str, token: str) -> Optional[User]:
        """Update one of the dedicated TTS OBS tokens."""
        if field_name not in {"tts_dock_token", "tts_source_token"}:
            raise ValueError("Unsupported TTS OBS token field")

        user = self.get_by_id(user_id)
        if user:
            setattr(user, field_name, token)
            self.db.commit()
            self.db.refresh(user)
            return user
        return None
    
    def create_with_obs_token(self, user_id: int, obs_token: str) -> User:
        """Create a new user with OBS token."""
        user = User(id=user_id, obs_token=obs_token)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user
