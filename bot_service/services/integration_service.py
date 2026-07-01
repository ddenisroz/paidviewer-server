# bot_service/services/integration_service.py
"""
Integration Service - Business logic for platform integrations.

Handles:
- Getting user integrations (Twitch, VK, DonationAlerts)
- Disconnecting integrations (bot leaves, keeps tokens)
- Removing integrations completely (deletes tokens)
"""
import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from core.database import User, UserToken
from core.token_utils import validate_platform_token
from repositories.user_repository import UserRepository
from repositories.user_token_repository import UserTokenRepository

logger = logging.getLogger('bot_service')


class IntegrationService:
    """Service for managing platform integrations."""

    def __init__(self, db: Session):
        self.db = db

    def _get_user_repo(self) -> UserRepository:
        return UserRepository(self.db)
    
    def _get_token_repo(self) -> UserTokenRepository:
        return UserTokenRepository(self.db)

    async def get_user_integrations(self, user_id: int) -> Dict[str, Dict[str, Any]]:
        """
        Get all active integrations for a user with token validation.
        
        Returns:
            Dict mapping platform name to integration info
        """
        integrations = {}
        
        try:
            token_repo = self._get_token_repo()
            user_repo = self._get_user_repo()
            
            user_tokens = token_repo.get_all_by_user(user_id)
            user_obj = user_repo.get(user_id)
            
            for token in user_tokens:
                if not token.access_token:
                    continue
                    
                # Validate token via platform API
                is_valid = await validate_platform_token(token)
                
                if not is_valid:
                    logger.warning(f"[WARN] Invalid token for {token.platform} user {user_id}")
                    continue
                
                # Get username from user object
                username = self._get_username_for_platform(token.platform, user_obj)
                
                integrations[token.platform] = {
                    "connected": True,
                    "username": username,
                    "platform_user_id": token.platform_user_id,
                    "avatar_url": token.avatar_url
                }
            
            return integrations
            
        except Exception:
            logger.exception("Error getting integrations")
            return {}

    def _get_username_for_platform(self, platform: str, user: Optional[User]) -> Optional[str]:
        """Get username for a specific platform from user object."""
        if not user:
            return None
        if platform == "twitch":
            return user.twitch_username
        elif platform == "vk":
            return user.vk_username
        elif platform == "donationalerts":
            return getattr(user, 'donationalerts_username', None)
        return None

    async def disconnect_integration(
        self,
        user_id: int,
        platform: str,
        connection_manager=None
    ) -> Dict[str, Any]:
        """
        Disconnect integration (bot leaves channel, tokens are deleted).
        
        This is a soft disconnect - bot leaves but can reconnect.
        """
        try:
            user_repo = self._get_user_repo()
            token_repo = self._get_token_repo()
            
            user = user_repo.get(user_id)
            if not user:
                return {"success": False, "error": "User not found"}

            channel_name = None
            
            if platform == "twitch":
                channel_name = user.twitch_username
                if channel_name:
                    await self._disconnect_twitch_bot(channel_name)
                    if connection_manager:
                        connection_manager.disable_tts_for_channel(channel_name.lower())
                        
            elif platform == "vk":
                channel_name = user.vk_channel_name or user.vk_username
                if channel_name:
                    await self._disconnect_vk_bot(channel_name)
                    if connection_manager:
                        connection_manager.disable_tts_for_channel(channel_name.lower())

            # Delete the token
            deleted = token_repo.delete_by_user_and_platform(user_id, platform)
            
            if deleted:
                logger.info(f"[OK] Deleted {platform} token for user {user_id}")

            logger.info(f"[OK] Integration {platform} disconnected for user {user_id}")
            return {"success": True, "message": f"{platform} bot disconnected"}

        except Exception:
            logger.exception("Error disconnecting {platform}")
            return {"success": False, "error": "Internal server error"}

    async def remove_integration(
        self,
        user_id: int,
        platform: str,
        connection_manager=None
    ) -> Dict[str, Any]:
        """
        Completely remove integration (delete tokens and disconnect).
        Requires re-authorization to reconnect.
        """
        try:
            # First disconnect
            disconnect_result = await self.disconnect_integration(
                user_id, platform, connection_manager
            )
            
            if not disconnect_result.get("success"):
                return disconnect_result

            # Remove token via session manager
            from core.session_manager import session_manager
            success = session_manager.remove_platform_token(user_id, platform)
            
            if not success:
               # Also try clearing via repo if session manager fails or is redundant
               self._get_token_repo().delete_by_user_and_platform(user_id, platform)

            logger.info(f"[OK] Integration {platform} REMOVED for user {user_id}")
            return {
                "success": True,
                "message": f"{platform} integration fully removed. Re-authorization required."
            }

        except Exception:
            logger.exception("Error removing {platform} integration")
            return {"success": False, "error": "Internal server error"}

    async def _disconnect_twitch_bot(self, channel_name: str) -> None:
        """Disconnect Twitch bot from channel."""
        try:
            from startup.bot_registry import get_bot_registry
            bot_instance = get_bot_registry().twitch_bot
            if bot_instance:
                await bot_instance.part_channels([channel_name])
                logger.info(f"[OK] Twitch bot left channel: {channel_name}")
        except Exception:
            logger.exception("Error disconnecting Twitch bot")
            raise

    async def _disconnect_vk_bot(self, channel_name: str) -> None:
        """Disconnect VK bot from channel."""
        try:
            from startup.bot_registry import get_bot_registry
            vk_bot = get_bot_registry().vk_bot
            if vk_bot:
                await vk_bot.disconnect_from_channel(channel_name)
                logger.info(f"[OK] Disconnected VK bot from {channel_name}")
        except Exception:
            logger.exception("Error disconnecting VK bot")
            raise

