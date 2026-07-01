from typing import Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException

from core.database import UserToken
from repositories.user_repository import UserRepository
from repositories.user_token_repository import UserTokenRepository
from core.token_encryption import decrypt_token as core_decrypt_token

class UserService:
    """
    Service for User related operations.
    Handles user data retrieval, token management, and platform specific user details.
    """
    def __init__(self):
        pass

    def _get_repository(self, db: Session) -> UserRepository:
        return UserRepository(db)

    def get_user_token(self, user_id: int, platform: str, db: Session) -> Optional[UserToken]:
        """Get user token for a specific platform."""
        repo = UserTokenRepository(db)
        return repo.get_by_user_and_platform(user_id, platform)

    def get_vk_channel_name(self, user_id: int, db: Session) -> str:
        """Get VK channel name for the user."""
        repo = self._get_repository(db)
        user = repo.get_by_id(user_id) # Using get_by_id from BaseRepository interface if available, or just get
        if not user:
             raise HTTPException(status_code=404, detail="VK channel is not configured.")
        channel_name = (user.vk_channel_name or "").strip()
        if not channel_name:
            fallback = (user.vk_username or "").strip()
            if fallback and " " not in fallback and "/" not in fallback:
                channel_name = fallback
        if not channel_name:
             raise HTTPException(status_code=404, detail="VK channel is not configured.")
        return channel_name

    def decrypt_access_token(self, encrypted_token: str) -> str:
        """Decrypt access token."""
        return core_decrypt_token(encrypted_token)

    def get_twitch_broadcaster_id(self, user_id: int, db: Session) -> str:
        """Get Twitch broadcaster ID (platform_user_id) for the user."""
        token = self.get_user_token(user_id, "twitch", db)
        if not token:
             raise HTTPException(status_code=404, detail="Twitch token not found. Please sign in again.")
        
        if not token.platform_user_id:
             raise HTTPException(status_code=404, detail="Twitch broadcaster ID not found.")
             
        return token.platform_user_id
