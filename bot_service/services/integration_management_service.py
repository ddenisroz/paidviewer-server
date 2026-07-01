# bot_service/services/integration_management_service.py
"""
Service for working with user integrations.
"""

import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

from sqlalchemy.orm import Session

from core.database import User, UserToken
from core.token_utils import validate_platform_token
from repositories.user_repository import UserRepository
from repositories.user_token_repository import UserTokenRepository

logger = logging.getLogger(__name__)


@dataclass
class IntegrationInfo:
    """Integration information."""
    platform: str
    connected: bool
    username: Optional[str]
    platform_user_id: Optional[str]
    avatar_url: Optional[str]


class IntegrationManagementService:
    """
    Service for working with user integrations.
    """
    
    async def get_user_integrations(
        self, 
        user_id: int, 
        db: Session
    ) -> Dict[str, IntegrationInfo]:
        """
        Return active user integrations after token validation.
        """
        token_repo = UserTokenRepository(db)
        user_repo = UserRepository(db)
        
        user_tokens = token_repo.get_all_by_user(user_id)
        user_obj = user_repo.get(user_id)
        
        integrations: Dict[str, IntegrationInfo] = {}
        
        for token in user_tokens:
            if not token.access_token:
                continue
                
            # Validate the token through the platform API.
            is_valid = await validate_platform_token(token)
            
            if is_valid:
                platform = token.platform
                username = self._get_username_for_platform(user_obj, platform)
                
                integrations[platform] = IntegrationInfo(
                    platform=platform,
                    connected=True,
                    username=username,
                    platform_user_id=token.platform_user_id,
                    avatar_url=token.avatar_url,
                )
            else:
                logger.warning(
                    f"[INTEGRATION] Invalid token for {token.platform} user {user_id}, "
                    "skipping (keeping token for retry)"
                )
        
        return integrations
    
    def _get_username_for_platform(
        self, 
        user: Optional[User], 
        platform: str
    ) -> Optional[str]:
        """Return platform username from a user object."""
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
        db: Session,
    ) -> bool:
        """
        Disconnect an integration and delete its token.
        """
        from core.connection_manager import get_connection_manager
        
        user_repo = UserRepository(db)
        token_repo = UserTokenRepository(db)
        
        db_user = user_repo.get(user_id)
        if not db_user:
            raise ValueError(f"User {user_id} not found")
        
        connection_manager = get_connection_manager()
        
        # Disconnect the bot from the channel.
        if platform == "twitch":
            await self._disconnect_twitch_bot(db_user, connection_manager)
        elif platform == "vk":
            await self._disconnect_vk_bot(db_user, connection_manager)
        
        # Delete the token.
        success = token_repo.delete_by_user_and_platform(user_id, platform)
        
        if success:
             logger.info(f"[INTEGRATION] Deleted {platform} token for user {user_id}")
        
        logger.info(f"[INTEGRATION] {platform} disconnected for user {user_id}")
        return True
    
    async def _disconnect_twitch_bot(self, user: User, connection_manager) -> None:
        """Disconnect the Twitch bot from the channel."""
        channel_name = user.twitch_username
        if not channel_name:
            return
            
        try:
            from startup.bot_registry import get_bot_registry
            bot_instance = get_bot_registry().twitch_bot
            if bot_instance:
                await bot_instance.part_channels([channel_name])
                logger.info(f"[INTEGRATION] Twitch bot left channel: {channel_name}")
            
            connection_manager.disable_tts_for_channel(channel_name.lower())
        except Exception:
            logger.exception("[INTEGRATION] Error disconnecting Twitch bot")
            raise
    
    async def _disconnect_vk_bot(self, user: User, connection_manager) -> None:
        """Disconnect the VK bot from the channel."""
        channel_name = user.vk_channel_name or user.vk_username
        if not channel_name:
            return
            
        try:
            from startup.bot_registry import get_bot_registry
            vk_bot = get_bot_registry().vk_bot
            if vk_bot:
                await vk_bot.disconnect_from_channel(channel_name)
                logger.info(f"[INTEGRATION] VK bot disconnected from {channel_name}")
            
            connection_manager.disable_tts_for_channel(channel_name.lower())
        except Exception:
            logger.exception("[INTEGRATION] Error disconnecting VK bot")
            raise
    
    async def remove_integration(
        self,
        user_id: int,
        platform: str,
        db: Session,
    ) -> bool:
        """
        Fully remove an integration.
        """
        from core.session_manager import session_manager
        from core.connection_manager import get_connection_manager
        
        user_repo = UserRepository(db)
        
        db_user = user_repo.get(user_id)
        if not db_user:
            raise ValueError(f"User {user_id} not found")
        
        connection_manager = get_connection_manager()
        
        # Disconnect the bot.
        if platform == "twitch":
            await self._disconnect_twitch_bot(db_user, connection_manager)
        elif platform == "vk":
            await self._disconnect_vk_bot(db_user, connection_manager)
        
        # Remove tokens through session_manager.
        success = session_manager.remove_platform_token(user_id, platform)
        if not success:
            # Fallback to direct repository delete.
            UserTokenRepository(db).delete_by_user_and_platform(user_id, platform)
        
        logger.info(f"[INTEGRATION] {platform} fully removed for user {user_id}")
        return True


# Singleton instance
integration_management_service = IntegrationManagementService()

