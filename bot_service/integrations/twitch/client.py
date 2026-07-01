# bot_service/integrations/twitch/client.py
"""
Twitch Helix API Client.

Pure HTTP client for working with the Twitch Helix API.
All methods accept a token explicitly; token management lives in oauth.py.
"""

import logging
from typing import Optional, Dict, Any, List

from aiohttp import ClientTimeout

from integrations.base import BaseIntegrationClient, TokenInfo, IntegrationError, TokenExpiredError
from .oauth import TwitchOAuth

logger = logging.getLogger(__name__)


class TwitchClient(BaseIntegrationClient):
    """
    Client for the Twitch Helix API.
    
    Usage examples:
        oauth = TwitchOAuth.from_settings()
        client = TwitchClient(oauth)
        
        # Request with an app token
        user_info = await client.get_user_by_login("streamer_name")
        
        # Request with a user token
        token = TokenInfo(access_token="<user_token>")
        await client.update_stream_title(broadcaster_id, "New Title", token)
    """
    
    BASE_URL = "https://api.twitch.tv/helix"
    
    def __init__(self, oauth: TwitchOAuth, timeout: Optional[ClientTimeout] = None):
        super().__init__(self.BASE_URL, timeout)
        self.oauth = oauth
    async def _request(
        self,
        method: str,
        endpoint: str,
        token: Optional[TokenInfo] = None,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
        data: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Override to handle App Token refresh."""
        try:
            return await super()._request(method, endpoint, token, params, json_data, data)
        except TokenExpiredError:
            # If the request did not include a user token, an app token was used.
            if token is None:
                logger.warning("[TWITCH] App token expired/invalid, forcing refresh...")
                try:
                    await self.oauth.get_app_access_token(force_refresh=True)
                    # Retry once
                    return await super()._request(method, endpoint, token, params, json_data, data)
                except Exception as e:
                    logger.error(f"[TWITCH] Failed to refresh app token during retry: {e}")
                    raise
            raise

    async def _get_headers(self, token: Optional[TokenInfo] = None) -> Dict[str, str]:
        """Build headers with Client-ID and Authorization."""
        if token:
            access_token = token.access_token
        else:
            # Use an app token for public requests.
            access_token = await self.oauth.get_app_access_token()
        
        return {
            "Client-ID": self.oauth.client_id,
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
    
    # ==================== Users ====================
    
    async def get_user_by_login(self, login: str) -> Optional[Dict[str, Any]]:
        """Get user information by login."""
        try:
            result = await self.get("users", params={"login": login})
            data = result.get("data", [])
            return data[0] if data else None
        except IntegrationError as e:
            logger.error(f"[TWITCH] Failed to get user {login}: {e}")
            return None
    
    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user information by ID."""
        try:
            result = await self.get("users", params={"id": user_id})
            data = result.get("data", [])
            return data[0] if data else None
        except IntegrationError as e:
            logger.error(f"[TWITCH] Failed to get user by ID {user_id}: {e}")
            return None
    
    async def get_user_from_token(self, token: TokenInfo) -> Optional[Dict[str, Any]]:
        """Get user information from the user's token."""
        try:
            result = await self.get("users", token=token)
            data = result.get("data", [])
            return data[0] if data else None
        except IntegrationError as e:
            logger.error(f"[TWITCH] Failed to get user from token: {e}")
            return None
    
    # ==================== Streams ====================
    
    async def get_stream_by_login(self, login: str) -> Optional[Dict[str, Any]]:
        """Get stream information by login."""
        try:
            result = await self.get("streams", params={"user_login": login})
            data = result.get("data", [])
            return data[0] if data else None
        except IntegrationError as e:
            logger.debug(f"[TWITCH] Failed to get stream {login}: {e}")
            return None
    
    async def get_stream_by_user_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get stream information by user ID."""
        try:
            result = await self.get("streams", params={"user_id": user_id})
            data = result.get("data", [])
            return data[0] if data else None
        except IntegrationError as e:
            logger.debug(f"[TWITCH] Failed to get stream for user {user_id}: {e}")
            return None
    
    # ==================== Channels ====================
    
    async def get_channel_info(self, broadcaster_id: str) -> Optional[Dict[str, Any]]:
        """Get channel information."""
        try:
            result = await self.get("channels", params={"broadcaster_id": broadcaster_id})
            data = result.get("data", [])
            return data[0] if data else None
        except IntegrationError as e:
            logger.error(f"[TWITCH] Failed to get channel {broadcaster_id}: {e}")
            return None
    
    async def update_channel(
        self, 
        broadcaster_id: str, 
        token: TokenInfo,
        title: Optional[str] = None,
        game_id: Optional[str] = None,
    ) -> bool:
        """
        Update channel information such as title and game.
        
        Requires scope: channel:manage:broadcast
        """
        data = {}
        if title is not None:
            data["title"] = title
        if game_id is not None:
            data["game_id"] = game_id
        
        if not data:
            return True
        
        try:
            await self.patch(
                f"channels?broadcaster_id={broadcaster_id}",
                token=token,
                json_data=data,
            )
            logger.info(f"[TWITCH] Channel {broadcaster_id} updated: {data}")
            return True
        except TokenExpiredError:
            raise
        except IntegrationError as e:
            logger.error(f"[TWITCH] Failed to update channel {broadcaster_id}: {e}")
            return False
    
    # ==================== Categories ====================
    
    async def search_categories(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search categories and games."""
        if not query or not query.strip():
            return []
        
        try:
            result = await self.get(
                "search/categories",
                params={"query": query.strip(), "first": str(limit)},
            )
            categories = result.get("data", [])
            
            # Format cover-image URLs
            for cat in categories:
                if 'box_art_url' in cat:
                    cat['box_art_url'] = cat['box_art_url'].replace('{width}x{height}', '285x380')
            
            return categories
        except IntegrationError as e:
            logger.error(f"[TWITCH] Failed to search categories '{query}': {e}")
            return []
    
    async def get_category_by_id(self, game_id: str) -> Optional[Dict[str, Any]]:
        """Get category information by ID."""
        try:
            result = await self.get("games", params={"id": game_id})
            data = result.get("data", [])
            return data[0] if data else None
        except IntegrationError as e:
            logger.error(f"[TWITCH] Failed to get category {game_id}: {e}")
            return None
    
    # ==================== Channel Points ====================
    
    async def get_custom_rewards(
        self, 
        broadcaster_id: str, 
        token: TokenInfo,
        only_manageable: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Get the list of custom channel rewards.
        
        Requires scope: channel:read:redemptions or channel:manage:redemptions
        """
        try:
            result = await self.get(
                "channel_points/custom_rewards",
                token=token,
                params={
                    "broadcaster_id": broadcaster_id,
                    "only_manageable_rewards": str(only_manageable).lower(),
                },
            )
            return result.get("data", [])
        except IntegrationError as e:
            logger.error(f"[TWITCH] Failed to get custom rewards: {e}")
            raise
    
    async def create_custom_reward(
        self,
        broadcaster_id: str,
        token: TokenInfo,
        reward_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Create a custom reward.
        
        Requires scope: channel:manage:redemptions
        """
        try:
            result = await self.post(
                f"channel_points/custom_rewards?broadcaster_id={broadcaster_id}",
                token=token,
                json_data=reward_data,
            )
            data = result.get("data", [])
            reward = data[0] if data else None
            if reward:
                logger.info(f"[TWITCH] Created reward: {reward_data.get('title')}")
            return reward
        except IntegrationError as e:
            logger.error(f"[TWITCH] Failed to create reward: {e}")
            raise
    
    async def update_custom_reward(
        self,
        broadcaster_id: str,
        reward_id: str,
        token: TokenInfo,
        reward_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Update a custom reward."""
        try:
            result = await self.patch(
                f"channel_points/custom_rewards?broadcaster_id={broadcaster_id}&id={reward_id}",
                token=token,
                json_data=reward_data,
            )
            data = result.get("data", [])
            return data[0] if data else None
        except IntegrationError as e:
            logger.error(f"[TWITCH] Failed to update reward {reward_id}: {e}")
            raise
    
    async def delete_custom_reward(
        self,
        broadcaster_id: str,
        reward_id: str,
        token: TokenInfo,
    ) -> bool:
        """Delete a custom reward."""
        try:
            await self.delete(
                f"channel_points/custom_rewards?broadcaster_id={broadcaster_id}&id={reward_id}",
                token=token,
            )
            logger.info(f"[TWITCH] Deleted reward {reward_id}")
            return True
        except IntegrationError as e:
            logger.error(f"[TWITCH] Failed to delete reward {reward_id}: {e}")
            return False
    
    # ==================== Moderation ====================
    
    async def add_moderator(
        self,
        broadcaster_id: str,
        user_id: str,
        token: TokenInfo,
    ) -> bool:
        """Add a moderator to a channel."""
        try:
            await self.post(
                "moderation/moderators",
                token=token,
                params={"broadcaster_id": broadcaster_id, "user_id": user_id},
            )
            logger.info(f"[TWITCH] Added moderator {user_id} to {broadcaster_id}")
            return True
        except IntegrationError as e:
            logger.error(f"[TWITCH] Failed to add moderator: {e}")
            return False
    
    async def remove_moderator(
        self,
        broadcaster_id: str,
        user_id: str,
        token: TokenInfo,
    ) -> bool:
        """Remove a moderator from a channel."""
        try:
            await self.delete(
                "moderation/moderators",
                token=token,
                params={"broadcaster_id": broadcaster_id, "user_id": user_id},
            )
            logger.info(f"[TWITCH] Removed moderator {user_id} from {broadcaster_id}")
            return True
        except IntegrationError as e:
            logger.error(f"[TWITCH] Failed to remove moderator: {e}")
            return False
    
    async def add_vip(
        self,
        broadcaster_id: str,
        user_id: str,
        token: TokenInfo,
    ) -> bool:
        """Add VIP status on a channel."""
        try:
            await self.post(
                "channels/vips",
                token=token,
                params={"broadcaster_id": broadcaster_id, "user_id": user_id},
            )
            logger.info(f"[TWITCH] Added VIP {user_id} to {broadcaster_id}")
            return True
        except IntegrationError as e:
            logger.error(f"[TWITCH] Failed to add VIP: {e}")
            return False
    
    async def remove_vip(
        self,
        broadcaster_id: str,
        user_id: str,
        token: TokenInfo,
    ) -> bool:
        """Remove VIP status from a channel."""
        try:
            await self.delete(
                "channels/vips",
                token=token,
                params={"broadcaster_id": broadcaster_id, "user_id": user_id},
            )
            logger.info(f"[TWITCH] Removed VIP {user_id} from {broadcaster_id}")
            return True
        except IntegrationError as e:
            logger.error(f"[TWITCH] Failed to remove VIP: {e}")
            return False

    # ==================== Redemptions ====================

    async def get_reward_redemptions(
        self,
        broadcaster_id: str,
        reward_id: str,
        token: TokenInfo,
        status: Optional[str] = None,
        sort: str = "OLDEST",
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get reward redemptions.
        
        Requires scope: channel:read:redemptions or channel:manage:redemptions
        """
        params = {
            "broadcaster_id": broadcaster_id,
            "reward_id": reward_id,
            "sort": sort,
            "first": str(limit)
        }
        if status:
            params["status"] = status  # UNFULFILLED, FULFILLED, CANCELED
            
        try:
            result = await self.get(
                "channel_points/custom_rewards/redemptions",
                token=token,
                params=params,
            )
            return result.get("data", [])
        except IntegrationError as e:
            logger.error(f"[TWITCH] Failed to get redemptions: {e}")
            raise

    async def update_redemption_status(
        self,
        broadcaster_id: str,
        reward_id: str,
        redemption_id: str,
        token: TokenInfo,
        status: str
    ) -> bool:
        """
        Update redemption status (FULFILLED or CANCELED).
        
        Requires scope: channel:manage:redemptions
        """
        try:
            result = await self.patch(
                f"channel_points/custom_rewards/redemptions?broadcaster_id={broadcaster_id}&id={redemption_id}&reward_id={reward_id}",
                token=token,
                json_data={"status": status},
            )
            logger.info(f"[TWITCH] Updated redemption {redemption_id} to {status}")
            return True
        except IntegrationError as e:
            logger.error(f"[TWITCH] Failed to update redemption status {redemption_id}: {e}")
            raise

    # ==================== Moderation (Bans/Timeouts) ====================

    async def ban_user(
        self,
        broadcaster_id: str,
        moderator_id: str,
        target_user_id: str,
        token: TokenInfo,
        duration: Optional[int] = None,
        reason: Optional[str] = None
    ) -> bool:
        """
        Ban or time out a user.
        
        Args:
            duration: If provided, this is a timeout in seconds. If None, this is a ban.
            
        Requires scope: moderator:manage:banned_users
        """
        params = {
            "broadcaster_id": broadcaster_id,
            "moderator_id": moderator_id
        }
        
        body_data = {"user_id": target_user_id}
        if duration is not None:
            body_data["duration"] = duration
        if reason:
            body_data["reason"] = reason
            
        body = {"data": body_data}
        
        try:
            await self.post(
                "moderation/bans",
                token=token,
                params=params,
                json_data=body
            )
            logger.info(f"[TWITCH] Banned/Timeout user {target_user_id} in {broadcaster_id}")
            return True
        except IntegrationError as e:
            logger.error(f"[TWITCH] Failed to ban user {target_user_id}: {e}")
            raise

    async def unban_user(
        self,
        broadcaster_id: str,
        moderator_id: str,
        target_user_id: str,
        token: TokenInfo
    ) -> bool:
        """
        Unban a user or remove a timeout.
        
        Requires scope: moderator:manage:banned_users
        """
        params = {
            "broadcaster_id": broadcaster_id,
            "moderator_id": moderator_id,
            "user_id": target_user_id
        }
        
        try:
            await self.delete(
                "moderation/bans",
                token=token,
                params=params
            )
            logger.info(f"[TWITCH] Unbanned user {target_user_id} in {broadcaster_id}")
            return True
        except IntegrationError as e:
            logger.error(f"[TWITCH] Failed to unban user {target_user_id}: {e}")
            raise

