"""
Twitch platform implementation
"""
import logging
from typing import Optional, Dict, Any, List
from .base import PlatformCapabilities, PlatformConfig, StreamingPlatform

# [REF] Integrations
from integrations.twitch.client import TwitchClient
from integrations.twitch.oauth import TwitchOAuth
from integrations.base import TokenInfo, TokenExpiredError

# [REF] Services
from services.user_service import UserService
from core.database import User, get_db
from repositories.user_token_repository import UserTokenRepository

logger = logging.getLogger(__name__)


class TwitchPlatform(StreamingPlatform):
    """Twitch streaming platform implementation"""

    def __init__(self):
        config = PlatformConfig(
            name='twitch',
            display_name='Twitch',
            supports_oauth=True,
            supports_chat=True,
            supports_tts=True,
            supports_points=True,
            supports_categories=True,
            color='#9146FF',
            capabilities=PlatformCapabilities(
                roles=True,
                badges=True,
                reply_context=True,
                mention_context=True,
                moderation_actions=True,
                rewards=True,
                bot_status=True,
                supported_roles=['owner', 'moderator', 'vip', 'subscriber', 'viewer'],
                moderation_actions_available=['timeout', 'ban', 'mod', 'vip'],
            ),
        )
        super().__init__(config)

        # Initialize Integration Components
        self.oauth = TwitchOAuth.from_settings()
        self.client = TwitchClient(self.oauth)
        self.user_service = UserService()

    async def _execute_with_token(self, user_id: int, operation, default_return=False):
        """
        Executes an operation with automatic token handling and refresh.
        operation: async function(token_info, broadcaster_id)
        """
        try:
            db = next(get_db())
            try:
                token = self.user_service.get_user_token(user_id, 'twitch', db)
                if not token:
                    logger.warning(f"No Twitch token found for user {user_id}")
                    return default_return
                
                decrypted_token = self.user_service.decrypt_access_token(token.access_token)
                token_info = TokenInfo(
                    access_token=decrypted_token,
                    refresh_token=token.refresh_token,
                    scopes=token.scopes
                )
                
                broadcaster_id = token.platform_user_id
                if not broadcaster_id:
                     user = await self.client.get_user_from_token(token_info)
                     if user:
                         broadcaster_id = user['id']
                
                if not broadcaster_id:
                    logger.error("Could not determine broadcaster ID")
                    return default_return

                try:
                    return await operation(token_info, broadcaster_id)
                except TokenExpiredError:
                    logger.warning(f"Twitch token expired for user {user_id}, attempting refresh...")
                    if not token.refresh_token:
                        logger.error("No refresh token available")
                        return default_return
                        
                    try:
                        new_tokens = await self.oauth.refresh_user_token(token.refresh_token)
                        
                        # Update DB
                        token_repo = UserTokenRepository(db)
                        token_repo.upsert(
                            user_id=user_id,
                            platform='twitch',
                            access_token=new_tokens.access_token,
                            refresh_token=new_tokens.refresh_token,
                            expires_at=None,
                            scopes=new_tokens.scopes
                        )
                        
                        # Retry with new token
                        new_token_info = TokenInfo(
                            access_token=new_tokens.access_token,
                            refresh_token=new_tokens.refresh_token,
                            scopes=new_tokens.scopes
                        )
                        logger.info("Retrying operation with new token")
                        return await operation(new_token_info, broadcaster_id)
                        
                    except Exception as refresh_error:
                        logger.error(f"Failed to refresh token: {refresh_error}")
                        return default_return
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error executing Twitch operation: {e}")
            return default_return

    async def authenticate(self, code: str) -> Dict[str, Any]:
        """
        Handle Twitch OAuth authentication
        
        Args:
            code: OAuth authorization code
            
        Returns:
            Dict containing access_token, refresh_token, expires_in, scopes
        """
        try:
            token_response = await self.oauth.exchange_code(code)
            
            # Map TwitchTokenResponse to Dict
            return {
                "access_token": token_response.access_token,
                "refresh_token": token_response.refresh_token,
                "expires_in": token_response.expires_in,
                "scope": token_response.scope, # Twitch returns 'scope' (list or string?) list in Helix usually, space separated string in response
                "token_type": token_response.token_type
            }
        except Exception as e:
            logger.error(f"Twitch authentication error: {e}")
            raise

    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """
        Get Twitch user information
        
        Args:
            access_token: User's access token
            
        Returns:
            Dict containing id, login, display_name, profile_image_url, etc.
        """
        try:
            # We construct TokenInfo with just access_token for this request
            token_info = TokenInfo(access_token=access_token)
            user_info = await self.client.get_user_from_token(token_info)
            
            if not user_info:
                raise Exception("Failed to get user info from Twitch")

            return user_info
        except Exception as e:
            logger.error(f"Error getting Twitch user info: {e}")
            raise

    async def update_stream_title(self, user_id: int, title: str) -> bool:
        """
        Update Twitch stream title
        
        Args:
            user_id: Unified user ID from database
            title: New stream title
            
        Returns:
            True if successful, False otherwise
        """
        async def op(token_info, broadcaster_id):
            return await self.client.update_channel(broadcaster_id, token_info, title=title)
            
        result = await self._execute_with_token(user_id, op, default_return=False)
        return bool(result)

    async def update_stream_category(self, user_id: int, category_id: str) -> bool:
        """
        Update Twitch stream category
        
        Args:
            user_id: Unified user ID from database
            category_id: Twitch game ID
            
        Returns:
            True if successful, False otherwise
        """
        async def op(token_info, broadcaster_id):
            return await self.client.update_channel(broadcaster_id, token_info, game_id=category_id)
            
        result = await self._execute_with_token(user_id, op, default_return=False)
        return bool(result)

    async def search_categories(self, query: str) -> List[Dict[str, Any]]:
        """
        Search for Twitch categories
        
        Args:
            query: Search query
            
        Returns:
            List of category dicts with id, name, box_art_url
        """
        try:
            # Uses App Token via client
            return await self.client.search_categories(query)
        except Exception as e:
            logger.error(f"Error searching Twitch categories: {e}")
            return []

    async def get_stream_status(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Get current Twitch stream status
        
        Args:
            username: Twitch username
            
        Returns:
            Dict with stream info if online, None if offline
        """
        try:
            return await self.client.get_stream_by_login(username)
        except Exception as e:
            logger.error(f"Error getting Twitch stream status: {e}")
            return None

    async def get_channel_info(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Get Twitch channel information
        
        Args:
            username: Twitch username
            
        Returns:
            Dict with channel info (title, game_name, etc.)
        """
        try:
            # TwitchClient.get_channel_info takes broadcaster_id, NOT username.
            # We need to resolve username to ID first.
            user = await self.client.get_user_by_login(username)
            if not user:
                return None
            return await self.client.get_channel_info(user['id'])
        except Exception as e:
            logger.error(f"Error getting Twitch channel info: {e}")
            return None

    async def send_chat_message(self, user_id: int, message: str) -> bool:
        """
        Send message to Twitch chat
        
        Args:
            user_id: Unified user ID from database
            message: Message to send
            
        Returns:
            True if successful, False otherwise
        """
        db = next(get_db())
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user or not user.twitch_username:
                logger.warning("Cannot send Twitch chat message: user %s or channel is missing", user_id)
                return False

            from startup.bot_registry import get_bot_registry

            registry = get_bot_registry()
            bot = registry.twitch_bot
            if not bot:
                logger.warning("Cannot send Twitch chat message: bot runtime is not available")
                return False

            target_channel = next(
                (
                    channel
                    for channel in getattr(bot, "connected_channels", [])
                    if getattr(channel, "name", "").lower() == user.twitch_username.lower()
                ),
                None,
            )

            if target_channel is None:
                logger.warning("Cannot send Twitch chat message: bot is not connected to %s", user.twitch_username)
                return False

            await target_channel.send(message)
            return True
        except Exception as error:
            logger.error("Error sending Twitch chat message: %s", error)
            return False
        finally:
            db.close()

    async def create_reward(self, user_id: int, reward_data: Dict) -> Optional[str]:
        """
        Create Twitch channel points reward
        
        Args:
            user_id: Unified user ID from database
            reward_data: Reward configuration
            
        Returns:
            Reward ID if successful, None otherwise
        """
        async def op(token_info, broadcaster_id):
            result = await self.client.create_custom_reward(broadcaster_id, token_info, reward_data)
            return result.get("id") if result else None
            
        return await self._execute_with_token(user_id, op, default_return=None)

    async def update_reward(self, user_id: int, reward_id: str, reward_data: Dict) -> bool:
        """
        Update Twitch channel points reward
        
        Args:
            user_id: Unified user ID from database
            reward_id: Twitch reward ID
            reward_data: Updated reward configuration
            
        Returns:
            True if successful, False otherwise
        """
        async def op(token_info, broadcaster_id):
            result = await self.client.update_custom_reward(broadcaster_id, reward_id, token_info, reward_data)
            return result is not None
            
        result = await self._execute_with_token(user_id, op, default_return=False)
        return bool(result)

    async def delete_reward(self, user_id: int, reward_id: str) -> bool:
        """
        Delete Twitch channel points reward
        
        Args:
            user_id: Unified user ID from database
            reward_id: Twitch reward ID
            
        Returns:
            True if successful, False otherwise
        """
        async def op(token_info, broadcaster_id):
            return await self.client.delete_custom_reward(broadcaster_id, reward_id, token_info)
            
        result = await self._execute_with_token(user_id, op, default_return=False)
        return bool(result)

    async def get_user_roles(self, username: str, channel_name: str) -> List[str]:
        """
        Get user roles on a Twitch channel
        
        Args:
            username: User's Twitch username
            channel_name: Channel name
            
        Returns:
            List of role strings (broadcaster, moderator, vip, subscriber, viewer)
        """
        # This would use the existing platform_role_checker utility
        try:
            # This requires author_data from chat context
            # For now, return empty list as it needs chat integration
            logger.debug(f"get_user_roles called for {username} on {channel_name}")
            return []
        except Exception as e:
            logger.error(f"Error getting Twitch user roles: {e}")
            return []
