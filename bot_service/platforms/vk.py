"""
VK Live platform implementation
"""
import logging
from typing import Optional, Dict, Any, List
from sqlalchemy import func, or_

from .base import PlatformCapabilities, PlatformConfig, StreamingPlatform

# [REF] Integrations
from integrations.vk.client import VKClient
from integrations.vk.oauth import VKOAuth
from integrations.base import TokenInfo

# [REF] Services
from services.user_service import UserService
from core.database import get_db, User

logger = logging.getLogger(__name__)


class VKPlatform(StreamingPlatform):
    """VK Live streaming platform implementation"""

    def __init__(self):
        config = PlatformConfig(
            name='vk',
            display_name='VK Live',
            supports_oauth=True,
            supports_chat=True,
            supports_tts=True,
            supports_points=True,
            supports_categories=True,
            color='#0077FF',
            capabilities=PlatformCapabilities(
                roles=True,
                badges=True,
                reply_context=True,
                mention_context=True,
                moderation_actions=False,
                rewards=True,
                bot_status=True,
                supported_roles=['owner', 'moderator', 'viewer'],
                moderation_actions_available=[],
            ),
        )
        super().__init__(config)

        # Initialize Integration Components
        self.oauth = VKOAuth()
        self.client = VKClient(self.oauth)
        self.user_service = UserService()
        self.last_error: Optional[str] = None

    @staticmethod
    def _normalize_channel_slug(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        candidate = value.strip()
        if not candidate:
            return None
        if candidate.startswith("http://") or candidate.startswith("https://"):
            candidate = candidate.rstrip("/").split("/")[-1]
        if " " in candidate or "/" in candidate:
            return None
        return candidate

    async def _get_user_context(self, user_id: int):
        """Helper to get token and channel info."""
        self.last_error = None
        db = next(get_db())
        try:
            token = self.user_service.get_user_token(user_id, 'vk', db)
            user = db.query(User).filter(User.id == user_id).first()
            
            if not token or not user:
                self.last_error = "VK token or user is missing"
                return None, None

            decrypted_token = self.user_service.decrypt_access_token(token.access_token)
            token_info = TokenInfo(
                access_token=decrypted_token,
                refresh_token=token.refresh_token,
                scopes=token.scopes
            )

            channel_name = self._normalize_channel_slug(user.vk_channel_name)
            if not channel_name:
                channel_name = self._normalize_channel_slug(user.vk_username)
            resolved_channel_name = None
            try:
                user_info = await self.client.get_current_user(token_info)
                user_profile = user_info.get("user") if isinstance(user_info, dict) and isinstance(user_info.get("user"), dict) else user_info
                if user_info:
                    channel_obj = user_info.get('channel') or {}
                    channel_url = channel_obj.get('url') if isinstance(channel_obj, dict) else None
                    channel_url = channel_url or user_info.get('channel_url')
                    if not channel_url and isinstance(user_profile, dict):
                        channel_url = user_profile.get("channel_url")
                    if not channel_url:
                        channels = user_info.get("channels")
                        if isinstance(channels, list) and channels:
                            first_channel = channels[0]
                            if isinstance(first_channel, dict):
                                channel_url = first_channel.get("url")
                    if channel_url:
                        resolved_channel_name = self._normalize_channel_slug(channel_url)
            except Exception as e:
                logger.warning(f"Failed to validate VK streamer profile: {e}")

            if resolved_channel_name:
                channel_name = resolved_channel_name

            invalid_channel_name = bool(channel_name and (' ' in channel_name or channel_name.startswith('http')))
            if not channel_name or invalid_channel_name:
                try:
                    user_info = await self.client.get_current_user(token_info)
                    user_profile = user_info.get("user") if isinstance(user_info, dict) and isinstance(user_info.get("user"), dict) else user_info
                    channel_url = None
                    if user_info:
                        channel_obj = user_info.get('channel') or {}
                        channel_url = channel_obj.get('url') if isinstance(channel_obj, dict) else None
                        channel_url = channel_url or user_info.get('channel_url')
                        if not channel_url and isinstance(user_profile, dict):
                            channel_url = user_profile.get("channel_url")
                        if not channel_url:
                            channels = user_info.get("channels")
                            if isinstance(channels, list) and channels:
                                first_channel = channels[0]
                                if isinstance(first_channel, dict):
                                    channel_url = first_channel.get("url")
                    if channel_url:
                        channel_name = self._normalize_channel_slug(channel_url)
                except Exception as e:
                    logger.warning(f"Failed to resolve VK channel URL: {e}")

            if channel_name and channel_name != user.vk_channel_name:
                try:
                    from repositories.user_repository import UserRepository
                    user_repo = UserRepository(db)
                    updates = {"vk_channel_name": channel_name}
                    if not user.vk_username:
                        updates["vk_username"] = channel_name
                    user_repo.update(user, updates)
                except Exception as e:
                    logger.warning(f"Failed to persist VK channel name: {e}")

            if not channel_name:
                self.last_error = self.last_error or "VK channel URL is not available for this account"
            return token_info, channel_name
        finally:
            db.close()

    async def authenticate(self, code: str) -> Dict[str, Any]:
        """
        Handle VK Live OAuth authentication
        
        Args:
            code: OAuth authorization code
            
        Returns:
            Dict containing access_token, refresh_token, expires_in, scopes
        """
        try:
            token_info = await self.oauth.exchange_code(code)
            return {
                "access_token": token_info.access_token,
                "refresh_token": token_info.refresh_token,
                "expires_in": token_info.expires_in,
                "scope": token_info.scopes
            }
        except Exception as e:
            logger.error(f"VK authentication error: {e}")
            raise

    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """
        Get VK Live user information
        
        Args:
            access_token: User's access token
            
        Returns:
            Dict containing user info
        """
        try:
            token_info = TokenInfo(access_token=access_token)
            user_info = await self.client.get_current_user(token_info)
            if not user_info:
                raise Exception("Failed to get user info from VK Live")
            return user_info
        except Exception as e:
            logger.error(f"Error getting VK user info: {e}")
            raise

    async def update_stream_title(self, user_id: int, title: str) -> bool:
        """
        Update VK Live stream title
        
        Args:
            user_id: Unified user ID from database
            title: New stream title
            
        Returns:
            True if successful, False otherwise
        """
        self.last_error = None
        try:
            token_info, channel_name = await self._get_user_context(user_id)
            if not token_info or not channel_name:
                logger.warning(f"No VK token or channel name for user {user_id}")
                self.last_error = self.last_error or "VK token or channel is not available"
                return False

            success = await self.client.update_stream(channel_name, token_info, title=title)
            if not success:
                self.last_error = self.client.last_error or "VK stream title update failed"
            return success
        except Exception as e:
            logger.error(f"Error updating VK stream title: {e}")
            self.last_error = str(e)
            return False

    async def update_stream_category(self, user_id: int, category_id: str) -> bool:
        """
        Update VK Live stream category
        
        Args:
            user_id: Unified user ID from database
            category_id: VK category ID
            
        Returns:
            True if successful, False otherwise
        """
        self.last_error = None
        try:
            token_info, channel_name = await self._get_user_context(user_id)
            if not token_info or not channel_name:
                logger.warning(f"No VK token or channel name for user {user_id}")
                self.last_error = self.last_error or "VK token or channel is not available"
                return False

            success = await self.client.update_stream(channel_name, token_info, category_id=category_id)
            if not success:
                self.last_error = self.client.last_error or "VK stream category update failed"
            return success
        except Exception as e:
            logger.error(f"Error updating VK stream category: {e}")
            self.last_error = str(e)
            return False

    async def search_categories(self, query: str) -> List[Dict[str, Any]]:
        """
        Search for VK Live categories
        
        Args:
            query: Search query
            
        Returns:
            List of category dicts with id, name, box_art_url
        """
        # VK search usually requires a user token. 
        # Platform abstraction assumes generic search, but VK API is strict.
        # We might need a system token or just return empty for unauthenticated search.
        logger.warning("search_categories called without user_id context (not supported by VK directly)")
        return []

    async def search_categories_for_user(self, query: str, user_id: int) -> List[Dict[str, Any]]:
        """
        Search for VK Live categories for a specific user
        
        Args:
            query: Search query
            user_id: User ID for authentication
            
        Returns:
            List of category dicts with id, name, box_art_url
        """
        try:
            token_info, _ = await self._get_user_context(user_id)
            if not token_info:
                return []
            
            return await self.client.search_categories(query, token_info)
        except Exception as e:
            logger.error(f"Error searching VK categories: {e}")
            return []

    async def get_stream_status(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Get current VK Live stream status
        
        Args:
            username: VK channel name
            
        Returns:
            Dict with stream info if online, None if offline
        """
        # VK usually needs channel_name (url)
        # Public info might be fetchable without token if we implement public scrapper or specific API
        # but VKClient.get_stream_info prefers a token.
        # Minimal implementation using just channel_name if Client supports it (it does pass token=None)
        try:
            # Construct dummy token or pass None
            return await self.client.get_stream_info(username, TokenInfo(access_token=""))
        except Exception as e:
            logger.error(f"Error getting VK stream status: {e}")
            return None

    async def get_stream_status_for_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Get current VK Live stream status for a specific user
        
        Args:
            user_id: User ID
            
        Returns:
            Dict with stream info
        """
        try:
            token_info, channel_name = await self._get_user_context(user_id)
            if not token_info or not channel_name:
                return None
            
            return await self.client.get_stream_info(channel_name, token_info)
        except Exception as e:
            logger.error(f"Error getting VK stream status: {e}")
            return None

    async def get_channel_info(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Get VK Live channel information
        
        Args:
            username: VK channel name
            
        Returns:
            Dict with channel info
        """
        # Reusing get_stream_info as it returns channel/stream data
        return await self.get_stream_status(username)

    async def send_chat_message(self, user_id: int, message: str) -> bool:
        """
        Send message to VK Live chat
        
        Args:
            user_id: Unified user ID from database
            message: Message to send
            
        Returns:
            True if successful, False otherwise
        """
        db = next(get_db())
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.warning("Cannot send VK chat message: user %s is missing", user_id)
                return False

            channel_name = user.vk_channel_name or user.vk_username
            if not channel_name:
                logger.warning("Cannot send VK chat message: no VK channel configured for user %s", user_id)
                return False

            from startup.bot_registry import get_bot_registry

            registry = get_bot_registry()
            bot = registry.vk_bot
            if not bot or not registry.is_vk_running():
                logger.warning("Cannot send VK chat message: VK bot runtime is not available")
                return False

            return await bot.send_message(channel_name, message)
        except Exception as error:
            logger.error("Error sending VK chat message: %s", error)
            return False
        finally:
            db.close()

    async def create_reward(self, user_id: int, reward_data: Dict) -> Optional[str]:
        """
        Create VK Live channel points reward
        
        Args:
            user_id: Unified user ID from database
            reward_data: Reward configuration
            
        Returns:
            Reward ID if successful, None otherwise
        """
        try:
            token_info, channel_name = await self._get_user_context(user_id)
            if not token_info or not channel_name:
                return None
            
            result = await self.client.create_custom_reward(channel_name, token_info, reward_data)
            return result.get("id") if result else None
        except Exception as e:
            logger.error(f"Error creating VK reward: {e}")
            return None

    async def update_reward(self, user_id: int, reward_id: str, reward_data: Dict) -> bool:
        """
        Update VK Live channel points reward
        
        Args:
            user_id: Unified user ID from database
            reward_id: VK reward ID
            reward_data: Updated reward configuration
            
        Returns:
            True if successful, False otherwise
        """
        try:
            token_info, channel_name = await self._get_user_context(user_id)
            if not token_info or not channel_name:
                return False
            
            return await self.client.update_custom_reward(channel_name, reward_id, token_info, reward_data)
        except Exception as e:
            logger.error(f"Error updating VK reward: {e}")
            return False

    async def delete_reward(self, user_id: int, reward_id: str) -> bool:
        """
        Delete VK Live channel points reward
        
        Args:
            user_id: Unified user ID from database
            reward_id: VK reward ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            token_info, channel_name = await self._get_user_context(user_id)
            if not token_info or not channel_name:
                return False
            
            return await self.client.delete_custom_reward(channel_name, reward_id, token_info)
        except Exception as e:
            logger.error(f"Error deleting VK reward: {e}")
            return False

    async def get_user_roles(self, username: str, channel_name: str) -> List[str]:
        """
        Get user roles on a VK Live channel
        
        Args:
            username: User's VK username
            channel_name: Channel name
            
        Returns:
            List of role strings (broadcaster, moderator, vip, viewer)
        """
        normalized_username = self._normalize_channel_slug(username) or str(username or "").strip().lower()
        normalized_channel = self._normalize_channel_slug(channel_name) or str(channel_name or "").strip().lower()

        roles: list[str] = []
        if normalized_username and normalized_channel and normalized_username == normalized_channel:
            roles.extend(["owner", "broadcaster"])

        if not normalized_username:
            return roles or ["viewer"]

        db = next(get_db())
        try:
            username_lower = str(username or "").strip().lower()
            user = db.query(User).filter(
                or_(
                    func.lower(User.vk_channel_name) == normalized_username,
                    func.lower(User.vk_username) == username_lower,
                )
            ).first()

            if user:
                user_channel_slug = self._normalize_channel_slug(user.vk_channel_name) or ""
                if user.vk_is_owner and (
                    not normalized_channel
                    or not user_channel_slug
                    or user_channel_slug == normalized_channel
                ):
                    roles.extend(["owner", "broadcaster"])

                if user.vk_is_moderator:
                    roles.append("moderator")

            if normalized_channel and "moderator" not in roles:
                channel_owner = db.query(User).filter(
                    or_(
                        func.lower(User.vk_channel_name) == normalized_channel,
                        func.lower(User.vk_username) == normalized_channel,
                    )
                ).first()

                if channel_owner:
                    token_record = self.user_service.get_user_token(channel_owner.id, 'vk', db)
                    if token_record and token_record.access_token:
                        decrypted_token = self.user_service.decrypt_access_token(token_record.access_token)
                        token_info = TokenInfo(
                            access_token=decrypted_token,
                            refresh_token=token_record.refresh_token,
                            scopes=token_record.scopes,
                        )
                        members = await self.client.get_chat_members(
                            channel_owner.vk_channel_name or normalized_channel,
                            token_info,
                        )
                        for member in members:
                            if not isinstance(member, dict):
                                continue
                            member_candidates = [
                                member.get("nick"),
                                member.get("name"),
                                member.get("login"),
                            ]
                            normalized_candidates = {
                                (
                                    self._normalize_channel_slug(candidate)
                                    or str(candidate or "").strip().lower()
                                )
                                for candidate in member_candidates
                                if candidate
                            }
                            if normalized_username not in normalized_candidates:
                                continue

                            if member.get("is_owner") or member.get("is_broadcaster"):
                                roles.extend(["owner", "broadcaster"])
                            if member.get("is_moderator"):
                                roles.append("moderator")
                            break
        except Exception as error:
            logger.error(f"Error getting VK roles: {error}")
        finally:
            db.close()

        if not roles:
            roles.append("viewer")

        return list(dict.fromkeys(roles))
