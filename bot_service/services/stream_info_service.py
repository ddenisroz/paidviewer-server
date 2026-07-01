import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from core.database import User
from platforms.registry import platform_registry
from services.stream_session_service import StreamSessionService

logger = logging.getLogger(__name__)

class StreamInfoService:
    """
    Service for managing stream information and updates across platforms.
    Interacts with PlatformRegistry and StreamSessionService.
    """

    def __init__(self, db: Session):
        self.db = db
        self.session_service = StreamSessionService(db)
        self.last_error_by_platform: Dict[str, str] = {}

    @staticmethod
    def _normalize_category_id(value: Optional[Any]) -> Optional[str]:
        """Normalize category identifiers from mixed provider payloads."""
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized or normalized.lower() in {"none", "null", "undefined"}:
            return None
        return normalized

    @staticmethod
    def _normalize_category_name(value: Optional[Any]) -> Optional[str]:
        """Normalize category display names from strings or nested objects."""
        if value is None:
            return None
        if isinstance(value, dict):
            candidate = value.get("title") or value.get("name")
        else:
            candidate = value
        if candidate is None:
            return None
        normalized = str(candidate).strip()
        return normalized or None

    def _apply_category_contract(self, platform_name: str, result: Dict[str, Any]) -> None:
        """Normalize stream info so frontend always receives one category contract."""
        if platform_name == "twitch":
            category_id = self._normalize_category_id(result.get("game_id") or result.get("category_id"))
            category_name = self._normalize_category_name(result.get("game") or result.get("game_name"))
            box_art_url = result.get("game_box_art_url") or result.get("box_art_url")

            category_payload: Dict[str, Any] = {}
            if category_id:
                category_payload["id"] = category_id
            if category_name:
                category_payload["name"] = category_name
                category_payload["title"] = category_name
            if box_art_url:
                category_payload["box_art_url"] = box_art_url

            result["game_id"] = category_id
            result["category_id"] = category_id
            result["game"] = category_name
            result["category_name"] = category_name
            result["category"] = category_payload if category_payload else None
            return

        category_payload: Dict[str, Any] = {}
        raw_category = result.get("category")
        category_id = self._normalize_category_id(result.get("category_id"))
        category_name = self._normalize_category_name(result.get("category_name")) or self._normalize_category_name(raw_category)

        if isinstance(raw_category, dict):
            category_id = category_id or self._normalize_category_id(raw_category.get("id"))
            if raw_category.get("box_art_url"):
                category_payload["box_art_url"] = raw_category.get("box_art_url")
            if raw_category.get("cover_url"):
                category_payload["cover_url"] = raw_category.get("cover_url")

        if category_id:
            category_payload["id"] = category_id
        if category_name:
            category_payload["name"] = category_name
            category_payload["title"] = category_name

        result["category_id"] = category_id
        result["category_name"] = category_name
        result["category"] = category_payload if category_payload else None

    async def get_stream_info(self, user_id: int, platform_name: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get stream info and update session tracking.
        """
        logger.info(f"[STREAM_INFO] Getting stream info for user_id={user_id}, platform={platform_name}")
        
        platform = platform_registry.get(platform_name)
        if not platform:
            logger.warning(f"[STREAM_INFO] Platform {platform_name} not found")
            return self._empty_info()

        # Get stream status from platform
        # Note: Platform implementations might vary in signature, ideally unified.
        # TwitchPlatform: get_stream_status(username) -> but we have user_id. 
        # We need a method get_stream_status_by_user_id on StreamingPlatform if possible.
        # But base.py has get_stream_status(username).
        
        # We need to resolve username.
        # We need to resolve username.
        from repositories.user_repository import UserRepository
        user = UserRepository(self.db).get(user_id)
        if not user:
            logger.warning(f"[STREAM_INFO] User {user_id} not found in database")
            return self._empty_info()
        
        username = None
        if platform_name == 'twitch':
            username = user.twitch_username
            logger.info(f"[STREAM_INFO] Twitch username: {username}")
        elif platform_name == 'vk':
            username = (user.vk_channel_name or "").strip()
            if not username:
                vk_username = (user.vk_username or "").strip()
                if vk_username and " " not in vk_username and "/" not in vk_username:
                    username = vk_username
            logger.info(f"[STREAM_INFO] VK channel slug: {username}")
            
        if not username:
            logger.warning(f"[STREAM_INFO] No username found for user {user_id} on platform {platform_name}")
            return self._empty_info()

        # Fetch Info
        # VKPlatform has get_stream_status_for_user(user_id) which handles tokens better.
        # TwitchPlatform uses get_stream_status(username) which handles generic lookup.
        stream_info = None
        
        if hasattr(platform, 'get_stream_status_for_user'):
            stream_info = await platform.get_stream_status_for_user(user_id)
            logger.info(f"[STREAM_INFO] get_stream_status_for_user result: {stream_info}")
        else:
            stream_info = await platform.get_stream_status(username)
            logger.info(f"[STREAM_INFO] get_stream_status result: {stream_info}")

        is_live = stream_info is not None and (stream_info.get('is_live') or stream_info.get('online') or stream_info.get('type') == 'live')
        logger.info(f"[STREAM_INFO] is_live: {is_live}")
        
        # Get Channel Info (title, game) if stream_info doesn't have it fully or we want offline info
        channel_info = None
        if not stream_info: # If offline, we still want title/game
            logger.info(f"[STREAM_INFO] Stream offline, fetching channel_info for {username}")
            channel_info = await platform.get_channel_info(username)
            logger.info(f"[STREAM_INFO] channel_info result: {channel_info}")
        
        # Unify Result
        result = self._empty_info()
        
        if stream_info:
            result.update(stream_info)
            result['is_live'] = is_live  # Use calculated is_live, not always True
            result['viewers'] = stream_info.get('viewer_count', 0)
            logger.info(f"[STREAM_INFO] Using stream_info, title: {result.get('title')}")
        elif channel_info:
            result.update(channel_info)
            result['is_live'] = False  # Channel info means stream is offline
            logger.info(f"[STREAM_INFO] Using channel_info, title: {result.get('title')}")
        else:
            logger.warning(f"[STREAM_INFO] No stream_info or channel_info available")
             
        # Session Tracking logic
        title = result.get('title', "")
        
        if is_live and username:
            self.session_service.get_or_create_active_session(
                user_id=user_id,
                session_id=session_id,
                channel_name=username.lower(),
                platform=platform_name,
                title=title
            )
        elif not is_live and username:
            self.session_service.end_session(
                user_id=user_id,
                session_id=session_id,
                channel_name=username.lower(),
                platform=platform_name
            )
             
        # Normalize keys for Frontend
        # Frontend expects: is_live, title, category, viewers, etc.
        # VK returns 'category' object or 'category_id'. Twitch returns 'game_name', 'game_id'.
        
        if platform_name == 'twitch':
            result['game'] = result.get('game_name') # Frontend expects 'game'
            
            # Fetch box_art_url for category image display
            game_id = result.get('game_id')
            if game_id and hasattr(platform, 'client'):
                try:
                    category_info = await platform.client.get_category_by_id(game_id)
                    if category_info and category_info.get('box_art_url'):
                        result['game_box_art_url'] = category_info['box_art_url']
                        logger.debug(f"[STREAM_INFO] Added box_art_url for game {game_id}")
                except Exception:
                    logger.debug(
                        "[STREAM_INFO] Could not fetch box_art_url for game %s",
                        game_id,
                        exc_info=True,
                    )

        self._apply_category_contract(platform_name, result)

        logger.info(f"[STREAM_INFO] Final result: title={result.get('title')}, game={result.get('game')}, is_live={result.get('is_live')}")
        return result

    async def update_stream(self, user_id: int, platform_name: str, title: Optional[str] = None, category_id: Optional[str] = None) -> bool:
        """
        Update stream title/category.
        """
        self.last_error_by_platform.pop(platform_name, None)
        platform = platform_registry.get(platform_name)
        if not platform:
            self.last_error_by_platform[platform_name] = f"Platform '{platform_name}' is not available"
            return False

        success = True
        if title is not None:
            if not await platform.update_stream_title(user_id, title):
                success = False

        if category_id is not None:
            if not await platform.update_stream_category(user_id, category_id):
                success = False

        if not success:
            platform_error = getattr(platform, "last_error", None)
            if platform_error:
                self.last_error_by_platform[platform_name] = str(platform_error)
            else:
                self.last_error_by_platform[platform_name] = "Stream update failed"

        return success

    async def search_categories(self, platform_name: str, query: str, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Search categories.
        """
        platform = platform_registry.get(platform_name)
        if not platform:
             return []
             
        if user_id and hasattr(platform, 'search_categories_for_user'):
             return await platform.search_categories_for_user(query, user_id)
        
        return await platform.search_categories(query)

    def _empty_info(self):
        return {
            "is_live": False,
            "title": "",
            "game_id": None,
            "game": None,
            "category_id": None,
            "category_name": None,
            "category": None,
            "viewers": 0,
            "started_at": None,
            "language": "ru"
        }
