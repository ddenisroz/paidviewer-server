
import logging
from typing import Optional, Dict, Any, List, Union
import aiohttp

from integrations.base import BaseIntegrationClient, TokenInfo, IntegrationError, RateLimitError
from utils.vk_channel_url import get_vk_channel_candidates
from integrations.vk.oauth import VKOAuth

logger = logging.getLogger(__name__)

class VKClient(BaseIntegrationClient):
    """
    VK Live API Client.
    """
    PROD_BASE_URL = "https://api.live.vkvideo.ru"
    DEV_BASE_URL = "https://apidev.live.vkvideo.ru"
    BASE_URL = PROD_BASE_URL
    
    def __init__(self, oauth: VKOAuth):
        super().__init__(self.BASE_URL)
        self.oauth = oauth
        self.last_error: Optional[str] = None

    @staticmethod
    def _normalize_category_id(value: Optional[Any]) -> Optional[str]:
        """Normalize category identifiers coming from mixed frontend/backend payloads."""
        if value is None:
            return None

        normalized = str(value).strip()
        if not normalized:
            return None
        if normalized.lower() in {"none", "null", "undefined"}:
            return None
        return normalized

    async def _get_headers(self, token: Optional[TokenInfo] = None) -> Dict[str, str]:
        """
        Headers with Authorization.
        """
        if not token or not token.access_token:
            # Some public endpoints might not need it, but most do.
            return {"Content-Type": "application/json"}
        return {
            "Authorization": f"Bearer {token.access_token}",
            "Content-Type": "application/json"
        }

    async def _request_with_base(
        self,
        base_url: str,
        method: str,
        endpoint: str,
        token: Optional[TokenInfo] = None,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Execute a request with a temporary base_url for production endpoints.
        """
        url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        headers = await self._get_headers(token)
        session = await self._get_session()

        last_error: Optional[Exception] = None
        for attempt in range(self.MAX_RETRIES):
            try:
                async with session.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json_data,
                    data=data,
                ) as response:
                    return await self._handle_response(response)
            except aiohttp.ClientError as e:
                last_error = e
                logger.warning(
                    f"[INTEGRATION] {self.__class__.__name__} request failed "
                    f"(attempt {attempt + 1}/{self.MAX_RETRIES}): {e}"
                )
                if attempt < self.MAX_RETRIES - 1:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)

        raise IntegrationError(
            f"Request failed after {self.MAX_RETRIES} attempts",
            original_error=last_error
        )

    # ==================== User ====================

    def _format_channel_url(self, channel_url: str) -> str:
        if not channel_url:
            return channel_url
        if channel_url.startswith('http://') or channel_url.startswith('https://'):
            return channel_url
        return f"https://live.vkvideo.ru/{channel_url}"

    async def get_current_user(self, token: TokenInfo) -> Optional[Dict[str, Any]]:
        """Get info about current user (streamer)."""
        try:
            result = await self.get("v1/current_user", token=token)
            data = result.get("data")

            # Dev API sometimes omits channel info; retry on prod to resolve channel URL.
            has_channel = False
            if isinstance(data, dict):
                channel_obj = data.get("channel") or {}
                channel_url = channel_obj.get("url") if isinstance(channel_obj, dict) else None
                has_channel = bool(channel_url or data.get("channel_url"))

            if not has_channel:
                try:
                    prod_result = await self._request_with_base(
                        self.PROD_BASE_URL,
                        "GET",
                        "v1/current_user",
                        token=token
                    )
                    prod_data = prod_result.get("data")
                    if isinstance(prod_data, dict):
                        return prod_data
                except IntegrationError as e:
                    logger.warning(f"[VK client] Failed to fetch user info from prod API: {e}")

            return data
        except IntegrationError as e:
            logger.error(f"[VK client] Failed to get user info: {e}")
            raise

    async def get_chat_members(self, channel_url: str, token: TokenInfo, limit: int = 200) -> List[Dict[str, Any]]:
        """Return currently visible chat/viewer members for a VK Live channel."""
        base_candidates = [self.PROD_BASE_URL, self.DEV_BASE_URL]
        channel_candidates = get_vk_channel_candidates(channel_url)
        last_error: Optional[Exception] = None

        for base_url in base_candidates:
            for candidate in channel_candidates:
                try:
                    response = await self._request_with_base(
                        base_url,
                        "GET",
                        "v1/chat/members",
                        token=token,
                        params={"channel_url": candidate, "limit": str(limit)},
                    )
                    data = response.get("data", {})
                    users = data.get("users") if isinstance(data, dict) else None
                    if isinstance(users, list):
                        return users
                except IntegrationError as error:
                    last_error = error
                    if error.status_code in {404, 405} or "channel_not_found" in str(error):
                        continue
                    raise

        if last_error:
            logger.warning(f"[VK client] Failed to load chat members for {channel_url}: {last_error}")
        return []

    async def get_chat_member(self, channel_url: str, user_id: Union[int, str], token: TokenInfo) -> Optional[Dict[str, Any]]:
        """Return detailed chat-member information for a VK Live user."""
        base_candidates = [self.PROD_BASE_URL, self.DEV_BASE_URL]
        channel_candidates = get_vk_channel_candidates(channel_url)
        last_error: Optional[Exception] = None

        for base_url in base_candidates:
            for candidate in channel_candidates:
                try:
                    response = await self._request_with_base(
                        base_url,
                        "GET",
                        "v1/chat/member",
                        token=token,
                        params={"channel_url": candidate, "user_id": str(user_id)},
                    )
                    data = response.get("data")
                    if isinstance(data, dict):
                        return data
                except IntegrationError as error:
                    last_error = error
                    if error.status_code in {404, 405} or "channel_not_found" in str(error):
                        continue
                    raise

        if last_error:
            logger.warning(f"[VK client] Failed to load chat member for {channel_url}/{user_id}: {last_error}")
        return None

    async def get_channel_roles(self, channel_url: str, token: TokenInfo) -> List[Dict[str, Any]]:
        """Return available channel role definitions for a VK Live channel."""
        base_candidates = [self.PROD_BASE_URL, self.DEV_BASE_URL]
        channel_candidates = get_vk_channel_candidates(channel_url)
        last_error: Optional[Exception] = None

        for base_url in base_candidates:
            for candidate in channel_candidates:
                try:
                    response = await self._request_with_base(
                        base_url,
                        "GET",
                        "v1/channel_roles",
                        token=token,
                        params={"channel_url": candidate},
                    )
                    data = response.get("data", {})
                    roles = data.get("roles") if isinstance(data, dict) else None
                    if isinstance(roles, list):
                        return roles
                except IntegrationError as error:
                    last_error = error
                    if error.status_code in {404, 405} or "channel_not_found" in str(error):
                        continue
                    raise

        if last_error:
            logger.warning(f"[VK client] Failed to load channel roles for {channel_url}: {last_error}")
        return []

    async def get_channel_user_roles(self, channel_url: str, user_id: Union[int, str], token: TokenInfo) -> List[Dict[str, Any]]:
        """Return role entries for a specific VK Live user on a channel."""
        base_candidates = [self.PROD_BASE_URL, self.DEV_BASE_URL]
        channel_candidates = get_vk_channel_candidates(channel_url)
        last_error: Optional[Exception] = None

        for base_url in base_candidates:
            for candidate in channel_candidates:
                try:
                    response = await self._request_with_base(
                        base_url,
                        "GET",
                        "v1/channel_roles/user",
                        token=token,
                        params={"channel_url": candidate, "user_id": str(user_id)},
                    )
                    data = response.get("data", {})
                    roles = data.get("roles") if isinstance(data, dict) else None
                    if isinstance(roles, list):
                        return roles
                except IntegrationError as error:
                    last_error = error
                    if error.status_code in {404, 405} or "channel_not_found" in str(error):
                        continue
                    raise

        if last_error:
            logger.warning(f"[VK client] Failed to load user channel roles for {channel_url}/{user_id}: {last_error}")
        return []

    # ==================== Stream ====================

    async def get_stream_info(self, channel_url: str, token: TokenInfo) -> Dict[str, Any]:
        """
        Get info about the stream.
        Note: VK requires 'channel_url', not just ID, for public read often.
        If using token, we might get it via current_user or specific endpoint.
        """
        # Based on vk_stream.py logic
        default_offline = {
            "online": False, "title": "Stream offline", "category": "Just Chatting",
            "viewer_count": 0, "started_at": ""
        }
        
        try:
            # Using token allows seeing drafts/latency info etc.
            data = None
            last_error: Optional[Exception] = None
            for candidate in get_vk_channel_candidates(channel_url):
                params = {"channel_url": candidate}
                try:
                    result = await self.get("v1/channel", token=token, params=params)
                    data = result.get("data", {})
                    if data:
                        logger.info(f"[VK client] Resolved channel via {candidate}")
                        break
                except IntegrationError as e:
                    last_error = e
                    if "channel_not_found" in str(e):
                        continue
                    raise
            if data is None:
                if last_error:
                    raise last_error
                return default_offline
            
            stream = data.get("stream")
            if stream and stream.get('status') == 'started':
                category = stream.get("category", {})
                return {
                    "online": True,
                    "title": stream.get("title", "Untitled stream"),
                    "category": category.get("title", "Uncategorized") if category else "Uncategorized",
                    "category_id": category.get("id") if category else None,
                    "viewer_count": stream.get("counters", {}).get("viewers", 0),
                    "started_at": stream.get("planned_at", ""),
                    "stream_key": stream.get("id", ""),
                    "description": stream.get("description", ""),
                     "thumbnail": stream.get("preview_url", "")
                }
            
            # Offline fallback
            title = "Stream offline"
            category_name = "Just Chatting"
            category_id = None
            if stream:
                 title = stream.get("title", title)
                 if stream.get("category"):
                     category_id = stream["category"].get("id")
                     category_name = stream["category"].get("title", category_name)

            return {
                **default_offline,
                "title": title,
                "category": category_name,
                "category_id": category_id
            }

        except IntegrationError as e:
            logger.error(f"[VK client] Failed to get stream info: {e}")
            return default_offline

    async def update_stream(self, channel_url: str, token: TokenInfo, title: Optional[str] = None, category_id: Optional[str] = None) -> bool:
        """
        Update stream title or category.
        Requires getting current state first to merge.
        """
        self.last_error = None
        try:
            base_candidates = [self.PROD_BASE_URL, self.DEV_BASE_URL]
            channel_candidates = get_vk_channel_candidates(channel_url)

            # 1. Get current state (try base + channel candidates)
            stream_info: Dict[str, Any] = {}
            last_error: Optional[Exception] = None
            for base_url in base_candidates:
                for candidate in channel_candidates:
                    try:
                        current_data = await self._request_with_base(
                            base_url,
                            "GET",
                            "v1/channel",
                            token=token,
                            params={"channel_url": candidate},
                        )
                        stream_info = current_data.get("data", {}).get("stream", {}) or {}
                        if stream_info:
                            logger.info(f"[VK client] Resolved stream info via {candidate} @ {base_url}")
                            break
                    except IntegrationError as e:
                        last_error = e
                        if e.status_code == 404 or "channel_not_found" in str(e):
                            continue
                        raise
                if stream_info:
                    break
            if not stream_info and last_error:
                logger.warning(f"[VK client] Failed to resolve stream info before update: {last_error}")

            # 2. Build payload
            current_cat_id = None
            if stream_info.get("category"):
                current_cat_id = stream_info["category"].get("id")

            payload = {
                "title": title if title is not None else stream_info.get("title", "")
            }
            requested_category_id = self._normalize_category_id(category_id)
            resolved_category_id = requested_category_id
            if not resolved_category_id:
                resolved_category_id = self._normalize_category_id(current_cat_id)
            if not resolved_category_id:
                try:
                    fallback_info = await self.get_stream_info(channel_url, token)
                    if isinstance(fallback_info, dict):
                        resolved_category_id = self._normalize_category_id(fallback_info.get("category_id"))
                except Exception as fallback_error:
                    logger.warning(f"[VK client] Failed fallback category resolution: {fallback_error}")

            if category_id is not None and not requested_category_id:
                self.last_error = "Invalid VK category id for stream update"
                return False

            # Keep existing category when available; allow title-only update without category.
            if resolved_category_id:
                payload["category"] = {"id": resolved_category_id}
            elif category_id is not None:
                logger.error(
                    "[VK client] Missing category.id for explicit category update "
                    "(channel=%s, requested_category=%s)",
                    channel_url,
                    category_id,
                )
                self.last_error = "Missing VK category id for stream update"
                return False
            if stream_info.get("description"):
                payload["description"] = stream_info.get("description")

            # 3. Update
            body = {"stream": payload}
            last_error = None
            endpoint_candidates = [
                "v1/channel/stream/edit",
                "v1/channel/edit",
                "v1/stream/edit",
            ]
            method_candidates = ["POST", "PATCH", "PUT"]

            for base_url in base_candidates:
                for endpoint in endpoint_candidates:
                    for method in method_candidates:
                        for candidate in channel_candidates:
                            try:
                                await self._request_with_base(
                                    base_url,
                                    method,
                                    endpoint,
                                    token=token,
                                    params={"channel_url": candidate},
                                    json_data=body
                                )
                                logger.info(
                                    f"[VK client] Updated stream via {method} {endpoint} "
                                    f"for {candidate} @ {base_url}"
                                )
                                return True
                            except IntegrationError as e:
                                last_error = e
                                if e.status_code in {404, 405}:
                                    continue
                                err_str = str(e)
                                if "unknown_api_method" in err_str or "channel_not_found" in err_str:
                                    continue
                                raise

            if last_error:
                if last_error.status_code == 405:
                    logger.warning(
                        "[VK client] Stream update methods are not supported by current VK API for channel %s",
                        channel_url,
                    )
                    self.last_error = "VK API does not support stream update for this channel/app"
                    return False
                self.last_error = str(last_error)
                raise last_error
            self.last_error = "VK stream update request failed"
            return False

        except IntegrationError as e:
            if e.status_code == 403:
                logger.warning("[VK client] Stream update forbidden for channel %s", channel_url)
                self.last_error = (
                    "VK denied stream update (403 forbidden). "
                    "Connected VK token has no stream-edit rights for this channel."
                )
                return False
            if e.status_code == 405:
                logger.warning(f"[VK client] Stream update is unsupported by VK API (405): {e}")
                self.last_error = "VK API does not support stream update for this channel/app"
                return False
            logger.error(f"[VK client] Failed to update stream: {e}")
            self.last_error = str(e)
            return False

    async def search_categories(self, query: str, token: TokenInfo) -> List[Dict[str, Any]]:
        """Search categories."""
        try:
            params = {"search": query, "type": "game", "limit": "20"}
            result = await self._request_with_base(
                self.PROD_BASE_URL,
                "GET",
                "v1/public_video_stream/category/",
                token=token,
                params=params
            )

            categories = []
            if isinstance(result, dict) and "data" in result:
                cats = result.get("data", [])
                for cat in cats:
                    if cat:
                        categories.append({
                            "id": cat.get("id"),
                            "name": cat.get("title"),
                            "box_art_url": cat.get("coverUrl")
                        })
            return categories
        except IntegrationError as e:
            logger.error(f"[VK client] Failed to search categories: {e}")
            return []

    # ==================== Rewards ====================

    async def get_custom_rewards(self, channel_url: str, token: TokenInfo) -> List[Dict[str, Any]]:
        """Get custom rewards."""
        try:
            result = await self.get("v1/channel_point/rewards", token=token, params={"channel_url": self._format_channel_url(channel_url)})
            return result.get("data", {}).get("rewards", [])
        except IntegrationError as e:
             logger.error(f"[VK client] Failed to get rewards: {e}")
             return []

    async def create_custom_reward(self, channel_url: str, token: TokenInfo, reward_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create reward."""
        try:
            body = {"reward": reward_data}
            result = await self.post("v1/channel_point/reward/create", token=token, 
                                   params={"channel_url": self._format_channel_url(channel_url)}, json_data=body)
            return result.get("data")
        except IntegrationError as e:
            logger.error(f"[VK client] Failed to create reward: {e}")
            return None

    async def delete_custom_reward(self, channel_url: str, reward_id: str, token: TokenInfo) -> bool:
        """Delete reward."""
        try:
            params = {"channel_url": self._format_channel_url(channel_url), "reward_id": reward_id}
            await self.post("v1/channel_point/reward/delete", token=token, params=params)
            return True
        except IntegrationError as e:
             logger.error(f"[VK client] Failed to delete reward: {e}")
             return False

    async def update_custom_reward(self, channel_url: str, reward_id: str, token: TokenInfo, reward_data: Dict[str, Any]) -> bool:
        """Update reward."""
        try:
            params = {"channel_url": self._format_channel_url(channel_url), "reward_id": reward_id}
            body = {"reward": reward_data}
            await self.post("v1/channel_point/reward/edit", token=token, params=params, json_data=body)
            return True
        except IntegrationError as e:
             logger.error(f"[VK client] Failed to update reward: {e}")
             return False
