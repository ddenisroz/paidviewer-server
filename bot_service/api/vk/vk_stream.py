"""
VK API Stream Module
Handles stream information, updates, and category management.
"""
import logging
from typing import Optional, Dict, Any, List, Union

import aiohttp

from core.database import SessionLocal
from .vk_auth import VKAuth
from .vk_base import VK_API_TIMEOUT
from utils.vk_channel_url import get_vk_channel_candidates

logger = logging.getLogger(__name__)

class VKStream(VKAuth):
    """
    Stream management methods for VK Live API.
    Refereces VKAuth for token management.
    """

    def _get_channel_url_from_db(self, user_id: str) -> Optional[str]:
        """Get cached vk_channel_name from database."""
        try:
            db = SessionLocal()
            try:
                from repositories.user_repository import UserRepository
                repo = UserRepository(db)
                user_record = repo.get_by_id(int(user_id))
                if user_record and user_record.vk_channel_name:
                    return user_record.vk_channel_name
                return None
            finally:
                db.close()
        except Exception:
            logger.exception("Error getting channel URL from DB for user %s", user_id)
            return None

    async def search_categories(self, query: str, user_id: Optional[str], session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search VK Live categories by name.
        Requires streamer token.
        """


        if not user_id:
            logger.warning("[VK API] Search categories called without user_id")
            return []
            
        token = self._get_user_token(user_id, session_id)
        if not token:
            logger.info(f"User {user_id} has not authorized VK Live via OAuth. Categories unavailable.")
            return []

        await self.rate_limiter.wait()
        
        # Production category search (per docs/api/VK/CATEGORY_SEARCH_GUIDE.md)
        prod_url = "https://api.live.vkvideo.ru/v1/public_video_stream/category/"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        deduped_categories: Dict[str, Dict[str, Any]] = {}
        try:
            async with aiohttp.ClientSession(timeout=VK_API_TIMEOUT) as session:
                for cat_type in ["game", "irl"]:
                    params: Dict[str, Union[str, int]] = {
                        "search": str(query or ""),
                        "type": str(cat_type),
                        "limit": 25
                    }
                    async with session.get(prod_url, params=params, headers=headers) as response:
                        if response.status != 200:
                            logger.warning(f"[VK SEARCH] Prod category search failed ({response.status}) for type={cat_type}")
                            continue
                        data = await response.json(content_type=None)
                        items = data.get("data")
                        if not isinstance(items, list):
                            logger.warning("[VK SEARCH] Unexpected category response shape")
                            continue
                        for item in items:
                            category = {
                                "id": item.get("id"),
                                "name": item.get("title") or item.get("name"),
                                "viewers": item.get("viewers", 0),
                                "box_art_url": item.get("coverUrl") or item.get("cover_url")
                            }
                            dedupe_key = str(category["id"] or "").strip() or str(category["name"] or "").strip().lower()
                            if not dedupe_key:
                                continue
                            previous = deduped_categories.get(dedupe_key)
                            if previous is None or int(category.get("viewers") or 0) > int(previous.get("viewers") or 0):
                                deduped_categories[dedupe_key] = category
        except Exception:
            logger.exception("[VK SEARCH] Prod category search error")
            return []

        categories = list(deduped_categories.values())
        logger.info(f"[VK SEARCH] Found {len(categories)} categories via prod search")
        return categories

    async def _get_online_categories(self, token: str) -> List[Dict[str, Any]]:
        """Fetch all categories with active streams (Fallback method)."""
        await self.rate_limiter.wait()
        url = "https://apidev.live.vkvideo.ru/v1/catalog/online_categories"
        headers = {"Authorization": f"Bearer {token}"}
        
        # Try to get more categories (default seems to be 10)
        params = {"limit": 100}
        
        categories = []
        try:
            async with aiohttp.ClientSession(timeout=VK_API_TIMEOUT) as session:
                # Use ssl_context for apidev just in case
                async with session.get(url, headers=headers, params=params, ssl=self.ssl_context) as response:
                    if response.status == 200:
                        data = await response.json(content_type=None)
                        
                        # DEBUG
                        cats = data.get("data", {}).get("categories", [])
                        logger.info(f"[VK DEBUG] online_categories found {len(cats)} raw categories (limit=100)")
                        
                        for cat in cats:
                            categories.append({
                                "id": cat.get("id"),
                                "name": cat.get("title"),
                                "viewers": cat.get("viewers", 0), # Top level viewers?
                                "box_art_url": cat.get("cover_url")
                            })
                    else:
                        logger.warning(f"[VK API] online_categories returned {response.status}")
                        text = await response.text()
                        logger.warning(f"[VK API] Body: {text[:200]}")

        except Exception:
            logger.exception("[VK API] Error fetching online_categories")
            
        return categories

    async def get_stream_info(self, user_id: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Get information about the current stream."""
        default_offline = {
            "online": False, "title": "Stream offline", "category": "Just Chatting",
            "viewer_count": 0, "started_at": "", "stream_key": "",
            "description": "", "thumbnail": ""
        }
        try:
            token = self._get_user_token(user_id, session_id)
            if not token:
                logger.info(f"User {user_id} has not authorized VK Live via OAuth. Stream info unavailable.")
                return {
                    **default_offline,
                    "title": "VK Live bot is running (stream info unavailable)",
                    "description": "Authorize through settings to retrieve stream information."
                }

            # Get cached channel_url from DB
            channel_url = self._get_channel_url_from_db(user_id)
            if not channel_url:
                logger.warning(f"Could not get channel URL for user {user_id} from database")
                return default_offline

            logger.info(f"[OK] [VK API] Using cached channel_url from DB: {channel_url}")

            await self.rate_limiter.wait()
            async with aiohttp.ClientSession(timeout=VK_API_TIMEOUT) as session:
                headers = {"Authorization": f"Bearer {token}"}
                url = f"{self.BASE_URL}/v1/channel"
                response_data = None
                for candidate in get_vk_channel_candidates(channel_url):
                    params = {"channel_url": candidate}
                    async with session.get(url, headers=headers, params=params, ssl=self.ssl_context) as response:
                        if response.status == 200:
                            response_data = await response.json()
                            if response_data:
                                logger.info(f"[OK] [VK API] Resolved channel via {candidate}")
                                break
                        elif response.status == 404:
                            continue
                        else:
                            logger.warning(f"Failed to get channel info for '{candidate}'. Status: {response.status}")
                            return default_offline

                if not response_data:
                    logger.warning(f"Failed to get channel info for '{channel_url}'. Status: 404")
                    return default_offline

                data = response_data
                
                if isinstance(data, dict) and "data" in data and "stream" in data["data"]:
                    stream = data["data"].get("stream")
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
                            "thumbnail": stream.get("preview_url", ""),
                        }
                    else:
                        # Offline processing
                        category_id = None
                        category_name = 'Just Chatting'
                        title = "Stream offline"
                        description = ""
                
                        if stream and isinstance(stream, dict):
                            if stream.get("category"):
                                category_id = stream["category"].get("id")
                                category_name = stream["category"].get("title", 'Just Chatting')
                            title = stream.get("title", "Stream offline")
                            description = stream.get("description", "")
                
                        return {
                            'online': False,
                            'title': title,
                            'category': category_name,
                            'category_id': category_id,
                            'viewer_count': 0,
                            'started_at': '',
                            'stream_key': '',
                            'description': description,
                            'thumbnail': ''
                        }
                else:
                    logger.warning(f"No 'stream' object in channel data for '{channel_url}'.")
                    return default_offline

        except Exception:
            logger.exception("Error getting VK stream info for %s", user_id)
            return default_offline

    async def _update_stream(self, user_id: str, payload: Dict[str, Any], session_id: Optional[str] = None) -> bool:
        """Helper to update stream data (title, category)."""
        try:
            logger.info(f"[VK API] _update_stream called for user {user_id} with payload: {payload}")

            token = self._get_user_token(user_id, session_id)
            if not token:
                logger.error(f"[ERROR] [VK API] No token found for user {user_id}")
                return False

            # Get cached channel_url from DB
            channel_url = self._get_channel_url_from_db(user_id)
            if not channel_url:
                logger.error(f"[ERROR] [VK API] Could not get channel URL for user {user_id}")
                return False
            channel_candidates = get_vk_channel_candidates(channel_url)

            async with aiohttp.ClientSession(timeout=VK_API_TIMEOUT) as session:
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                
                # STEP 1: Get current stream to merge data
                current_stream_data = {}
                base_candidates = ["https://api.live.vkvideo.ru", self.BASE_URL]
                for base_url in base_candidates:
                    for candidate in channel_candidates:
                        get_url = f"{base_url}/v1/channel"
                        get_params = {"channel_url": candidate}
                        async with session.get(get_url, headers={"Authorization": f"Bearer {token}"}, params=get_params, ssl=self.ssl_context) as response:
                            if response.status == 200:
                                data = await response.json()
                                stream_object = data.get("data", {}).get("stream")
                                if stream_object and stream_object.get("status") == "started":
                                    current_stream_data = stream_object
                                else:
                                    streams_array = data.get("data", {}).get("streams", [])
                                    for s in streams_array:
                                        if s.get("status") == "started":
                                            current_stream_data = s
                                            break
                                if current_stream_data:
                                    logger.info(f"[OK] [VK API] Resolved channel for update via {candidate} @ {base_url}")
                                    break
                            elif response.status == 404:
                                continue
                        if current_stream_data:
                            break
                    if current_stream_data:
                        break
                
                if not current_stream_data:
                    # Fallback to get_stream_info logic if not found active
                    stream_info = await self.get_stream_info(user_id)
                    if stream_info and stream_info.get("category_id"):
                        current_stream_data = {
                            "title": stream_info.get("title", ""),
                            "category": {"id": str(stream_info["category_id"])} 
                        }

                # STEP 2: Build final payload
                current_category_id = current_stream_data.get("category", {}).get("id")
                if current_category_id is not None:
                    current_category_id = str(current_category_id)

                final_payload = {
                    "title": current_stream_data.get("title", ""),
                    "category": {
                        "id": current_category_id if current_category_id else ""
                    }
                }

                if current_stream_data.get("description"):
                    final_payload["description"] = current_stream_data.get("description")

                # Override with new data
                if "title" in payload:
                    final_payload["title"] = payload["title"]

                if "category" in payload:
                    if "id" in payload["category"]:
                        category_id = str(payload["category"]["id"])
                        
                        # Load full category info if we only have ID but want to be safe
                        # The logic from monolithic file was complex handling 'cover_url' requirements
                        # Here we try to simplify: if we have full object, use it. If not, try to fetch or use ID.
                        
                        if "title" in payload["category"]:
                            # We have full object
                            category_obj = {
                                "id": category_id,
                                "title": payload["category"].get("title", ""),
                                "type": payload["category"].get("type", "games")
                            }
                            # Only add cover_url if present
                            if payload["category"].get("cover_url"):
                                category_obj["cover_url"] = payload["category"]["cover_url"]
                            
                            final_payload["category"] = category_obj
                        else:
                            # We only have ID, try to fetch full info because VK API is picky
                            try:
                                cat_url = f"{self.BASE_URL}/v1/category"
                                cat_params = {"category_id": category_id}
                                async with session.get(cat_url, headers=headers, params=cat_params, ssl=self.ssl_context) as cat_res:
                                    if cat_res.status == 200:
                                        cat_data = await cat_res.json()
                                        full_category = cat_data.get("data", {}).get("category", {})
                                        if full_category:
                                            category_obj = {
                                                "id": category_id,
                                                "title": full_category.get("title", ""),
                                                "type": full_category.get("type", "games")
                                            }
                                            if full_category.get("cover_url"):
                                                category_obj["cover_url"] = full_category["cover_url"]
                                            final_payload["category"] = category_obj
                                        else:
                                             final_payload["category"]["id"] = category_id
                                    else:
                                        final_payload["category"]["id"] = category_id
                            except Exception:
                                final_payload["category"]["id"] = category_id

                # Ensure ID is present
                if not final_payload["category"].get("id"):
                    logger.error("[ERROR] [VK API] Missing category ID for update")
                    return False

                # STEP 3: Send Update
                await self.rate_limiter.wait()
                post_data = {"stream": final_payload}
                for base_url in base_candidates:
                    for candidate in channel_candidates:
                        post_url = f"{base_url}/v1/channel/stream/edit"
                        post_params = {"channel_url": candidate}
                        async with session.post(post_url, headers=headers, json=post_data, params=post_params, ssl=self.ssl_context) as response:
                            if response.status == 200:
                                logger.info(f"[OK] [VK API] Successfully updated stream for user {user_id} via {candidate} @ {base_url}")
                                return True
                            if response.status == 404:
                                continue
                            logger.error(f"[ERROR] [VK API] Stream edit failed: {response.status} - {await response.text()}")
                            return False

                logger.error("[ERROR] [VK API] Stream edit failed: all channel_url candidates returned 404")
                return False

        except Exception:
            logger.exception("[ERROR] [VK API] Error updating stream for user %s", user_id)
            return False

    async def update_stream_title(self, user_id: str, title: str, session_id: Optional[str] = None) -> bool:
        """Update stream title."""
        # Get current category to preserve it
        current_stream_info = await self.get_stream_info(user_id, session_id)
        payload: Dict[str, Any] = {"title": title}

        if current_stream_info and current_stream_info.get("category_id"):
            category_data_fixed: Dict[str, Any] = {"id": str(current_stream_info["category_id"])}
            payload["category"] = category_data_fixed

        return await self._update_stream(user_id, payload, session_id)

    async def update_stream_category(self, user_id: str, category_data: Union[str, Dict[str, Any]], session_id: Optional[str] = None) -> bool:
        """Update stream category."""
        # Get current title to preserve it
        current_stream_info = await self.get_stream_info(user_id, session_id)
        
        # Prepare category object
        if isinstance(category_data, dict):
            category_obj = {
                "id": str(category_data.get("id", "")),
                "title": category_data.get("title", ""),
                "type": category_data.get("type", "games")
            }
            if category_data.get("cover_url"):
                category_obj["cover_url"] = category_data["cover_url"]
        else:
            category_obj = {"id": str(category_data)}

        payload = {"category": category_obj}

        if current_stream_info and current_stream_info.get("title"):
            payload["title"] = current_stream_info["title"]

        return await self._update_stream(user_id, payload, session_id)
    
    async def get_categories(self, search: str = "", user_id: Optional[str] = None, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Wraps search_categories for compatibility."""
        return await self.search_categories(search, user_id, session_id)

    async def get_viewer_count(self, user_id: str) -> int:
        """Get live viewer count."""
        stream_info = await self.get_stream_info(user_id)
        if stream_info and stream_info.get("online"):
            return int(stream_info.get("viewer_count", 0))
        return 0

