# bot_service/services/bot_control_service.py

import logging
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from core.database import User
from core.connection_manager import get_connection_manager, ConnectionManager
from core.token_manager import token_manager
from core.datetime_utils import utcnow_naive
from models.bot_token import BotToken
from startup.bot_registry import get_bot_registry, BotRegistry

logger = logging.getLogger(__name__)

class BotControlService:
    """
    Service for managing bot connections (Twitch/VK) and checking status.
    Encapsulates logic previously found in bot_control_api.py.
    """

    def __init__(self):
        # We access singletons here, or we could pass them in __init__
        # For now, following the existing pattern of global getters
        pass

    def _get_connection_manager(self) -> ConnectionManager:
        return get_connection_manager()

    def _get_registry(self) -> BotRegistry:
        return get_bot_registry()

    def _get_user_tokens(self, user_id: int, db: Session) -> Dict[str, Optional[Dict[str, Any]]]:
        return {
            "twitch": token_manager.get_user_token_data(
                user_id, "twitch", require_session_check=False, db=db
            ),
            "vk": token_manager.get_user_token_data(
                user_id, "vk", require_session_check=False, db=db
            ),
        }

    def _get_bot_token_state(self, db: Session, platform: str) -> Dict[str, Any]:
        token = (
            db.query(BotToken)
            .filter(
                BotToken.platform == platform,
                BotToken.is_active.is_(True),
                BotToken.access_token.isnot(None),
            )
            .first()
        )

        if not token:
            return {
                "configured": False,
                "expired": False,
                "login": None,
                "auth_path": f"/auth/{platform}/bot/login",
            }

        expired = bool(token.expires_at and token.expires_at <= utcnow_naive())
        return {
            "configured": True,
            "expired": expired,
            "login": token.bot_login,
            "auth_path": f"/auth/{platform}/bot/login",
        }

    def _platform_status(
        self,
        *,
        platform: str,
        token_data: Optional[Dict[str, Any]],
        channel_name: Optional[str],
        runtime_running: bool,
        channel_active: bool,
        db: Session,
    ) -> Dict[str, Any]:
        bot_token = self._get_bot_token_state(db, platform)

        status = {
            "connected": False,
            "channel": channel_name,
            "user_integration": bool(token_data),
            "runtime_running": runtime_running,
            "bot_oauth": bot_token,
            "ready": False,
            "reason": None,
            "action": None,
        }

        if not token_data:
            status["reason"] = "platform_not_connected"
            status["action"] = f"/auth/{platform}/login"
            return status

        if not channel_name:
            status["reason"] = "channel_missing"
            return status

        if not bot_token["configured"]:
            status["reason"] = "bot_oauth_missing"
            status["action"] = bot_token["auth_path"]
            return status

        if bot_token["expired"]:
            status["reason"] = "bot_oauth_expired"
            status["action"] = bot_token["auth_path"]
            return status

        if not runtime_running:
            status["reason"] = "bot_runtime_offline"
            return status

        if not channel_active:
            status["reason"] = "channel_not_joined"
            return status

        status["connected"] = True
        status["ready"] = True
        return status

    def _build_status(self, user_id: int, user_record: User, db: Session) -> Dict[str, Any]:
        tokens = self._get_user_tokens(user_id, db)
        connection_manager = self._get_connection_manager()
        registry = self._get_registry()

        twitch_channel = user_record.twitch_username
        vk_channel = user_record.vk_channel_name

        twitch_running = registry.is_twitch_running()
        vk_running = registry.is_vk_running()

        twitch_active = bool(
            twitch_running
            and twitch_channel
            and connection_manager.is_channel_active(twitch_channel)
        )
        vk_active = bool(
            vk_running
            and vk_channel
            and connection_manager.is_channel_active(vk_channel)
        )

        twitch_status = self._platform_status(
            platform="twitch",
            token_data=tokens["twitch"],
            channel_name=twitch_channel,
            runtime_running=twitch_running,
            channel_active=twitch_active,
            db=db,
        )
        vk_status = self._platform_status(
            platform="vk",
            token_data=tokens["vk"],
            channel_name=vk_channel,
            runtime_running=vk_running,
            channel_active=vk_active,
            db=db,
        )

        connected_platforms = [
            platform
            for platform, status in (("twitch", twitch_status), ("vk", vk_status))
            if status["connected"]
        ]
        primary_platform = connected_platforms[0] if connected_platforms else None
        primary_status = (
            twitch_status
            if primary_platform == "twitch"
            else vk_status
            if primary_platform == "vk"
            else None
        )

        return {
            "connected": bool(connected_platforms),
            "ready": bool(connected_platforms),
            "channel": primary_status["channel"] if primary_status else None,
            "platform": primary_platform,
            "last_activity": None,
            "last_message": None,
            "twitch": twitch_status,
            "vk": vk_status,
        }

    def _connectivity_problem(self, status: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        candidate_reasons = []
        for platform in ("twitch", "vk"):
            platform_status = status[platform]
            if platform_status["user_integration"] and not platform_status["ready"]:
                candidate_reasons.append((platform, platform_status["reason"], platform_status.get("action")))

        if not candidate_reasons:
            return None

        reason_priority = {
            "bot_oauth_missing": 0,
            "bot_oauth_expired": 1,
            "bot_runtime_offline": 2,
            "channel_not_joined": 3,
            "channel_missing": 4,
        }
        platform, reason, action = sorted(
            candidate_reasons,
            key=lambda item: reason_priority.get(item[1] or "", 99),
        )[0]

        messages = {
            "bot_oauth_missing": "Нужно подключить отдельную авторизацию бота.",
            "bot_oauth_expired": "Авторизация бота истекла, подключите ее заново.",
            "bot_runtime_offline": "Сервис бота сейчас не запущен.",
            "channel_not_joined": "Бот еще не присоединился к каналу.",
            "channel_missing": "У интеграции нет имени канала.",
        }
        return {
            "code": reason,
            "platform": platform,
            "action": action,
            "message": messages.get(reason, "Бот пока не готов к работе с чатом."),
        }

    def get_bot_status(self, user_id: int, user_record: User, db: Session) -> Dict[str, Any]:
        """
        Get the current connection status of bots for the user.
        """
        return self._build_status(user_id, user_record, db)

    def connect_chat(self, user_id: int, user_record: User, db: Session) -> Dict[str, Any]:
        """
        Initiate connection for available platforms.
        """
        status = self._build_status(user_id, user_record, db)
        has_platform = status["twitch"]["user_integration"] or status["vk"]["user_integration"]

        if not has_platform:
            return {
                "success": False,
                "code": "platform_not_connected",
                "message": "Сначала подключите Twitch или VK Live.",
                "status": status,
            }

        problem = self._connectivity_problem(status)
        if problem and not status["connected"]:
            return {
                "success": False,
                **problem,
                "status": status,
            }

        connected_platforms = [
            label
            for label, platform in (("Twitch", "twitch"), ("VK Live", "vk"))
            if status[platform]["connected"]
        ]

        if connected_platforms:
             return {
                "success": True,
                "message": f"Бот подключен к: {', '.join(connected_platforms)}",
                "status": status,
            }

        return {
            "success": False,
            "code": "bot_not_ready",
            "message": "Бот пока не готов к работе с чатом.",
            "status": status,
        }

    def disconnect_chat(self, user_id: int, user_record: User, db: Session) -> Dict[str, Any]:
        """
        Disconnect bot from user channels.
        """
        # Note: logic requires fetching token from DB? api used get_user_token_from_db
        # But token_manager.get_user_token_data is cached.
        # The original API used `get_user_token_from_db` imported from core.token_utils.
        # I'll use token_manager for consistency if possible, or stick to utils if needed for "freshness"?
        # Actually disconnect probably doesn't need the token value, just existence to know if we SHOULD disconnect.
        # But wait, connection_manager needs channel name. User record has it.
        # Original code checked for token existence before trying to disconnect.

        # Let's use token_manager for existence check.
        tokens = self._get_user_tokens(user_id, db)
        
        connection_manager = self._get_connection_manager()
        disconnected = []

        if tokens["twitch"] and user_record.twitch_username:
            channel_name = user_record.twitch_username
            if connection_manager.remove_active_session(channel_name, "manual_disconnect"):
                disconnected.append("Twitch")

        if tokens["vk"] and user_record.vk_channel_name:
             channel_name = user_record.vk_channel_name
             if connection_manager.remove_active_session(channel_name, "manual_disconnect"):
                 disconnected.append("VK Live")

        if disconnected:
             return {
                "success": True,
                "message": f"Bot disconnected from: {', '.join(disconnected)}"
            }
        else:
             return {
                "success": True,
                "message": "Bot was not connected."
            }
            
    def get_chat_status(self, user_id: int, user_record: User, db: Session) -> Dict[str, Any]:
         # Logic similar to get_bot_status but returns specific chat structure
         status = self._build_status(user_id, user_record, db)
         return {
            "connected": status["connected"],
            "ready": status["ready"],
            "channel": status["channel"],
            "platform": status["platform"],
            "last_message": None,
            "twitch": status["twitch"],
            "vk": status["vk"],
        }

    def reconnect_chat(self, user_id: int, user_record: User, db: Session) -> Dict[str, Any]:
        tokens = self._get_user_tokens(user_id, db)

        if not tokens["twitch"] and not tokens["vk"]:
             return {"success": False, "error": "No connected platforms."}

        connection_manager = self._get_connection_manager()
        reconnected = []

        if tokens["twitch"] and user_record.twitch_username:
             channel_name = user_record.twitch_username
             connection_manager.remove_active_session(channel_name, "reconnect")
             reconnected.append("Twitch")

        if tokens["vk"] and user_record.vk_channel_name:
             channel_name = user_record.vk_channel_name
             connection_manager.remove_active_session(channel_name, "reconnect")
             reconnected.append("VK Live")

        if reconnected:
             return {
                "success": True,
                "message": f"Reconnect initiated for: {', '.join(reconnected)}"
            }
        else:
             return {"success": False, "error": "Failed to initiate reconnect."}
