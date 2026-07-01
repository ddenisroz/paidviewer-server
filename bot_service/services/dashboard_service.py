# bot_service/services/dashboard_service.py
"""
Service for Dashboard functionality.
Aggregates data from various domains to provide a unified dashboard view.
"""
import logging
import json
from typing import Optional, Dict, Any, List

from sqlalchemy.orm import Session

from repositories.user_repository import UserRepository
from repositories.user_token_repository import UserTokenRepository
from repositories.tts_settings_repository import TTSSettingsRepository
from repositories.audio_settings_repository import AudioSettingsRepository
from repositories.chat_message_repository import ChatMessageRepository
from core.token_utils import validate_platform_token
from models.user import User

logger = logging.getLogger(__name__)


class DashboardService:
    """
    Service for Dashboard operations.
    Aggregates data for the frontend dashboard initialization.
    """

    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)
        self.token_repo = UserTokenRepository(db)
        self.tts_repo = TTSSettingsRepository(db)
        self.audio_repo = AudioSettingsRepository(db)
        self.chat_repo = ChatMessageRepository(db)

    async def get_dashboard_init_data(self, current_user: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Get all initial data for the dashboard.
        
        Returns:
            Dict containing user, integrations, tts, and chat_history data.
        """
        # Default empty response structure
        response = {
            "success": True,
            "user": None,
            "integrations": {},
            "tts": None,
            "chat_history": []
        }

        if not current_user:
            return response

        try:
            user_id = current_user.get("id")
            if not user_id:
                # Should not happen for authenticated user, but safe fallback
                return response

            # 1. Get User Data
            db_user = self.user_repo.get_by_id(user_id)
            if not db_user:
                return response

            response["user"] = {
                "id": db_user.id,
                "twitch_username": db_user.twitch_username,
                "vk_username": db_user.vk_username,
                "vk_channel_name": db_user.vk_channel_name,
                "is_admin": db_user.is_admin,
                "created_at": db_user.created_at.isoformat() if db_user.created_at else None
            }

            # 2. Get Integrations Status
            response["integrations"] = await self._get_integrations(user_id, db_user)

            # 3. Get TTS Settings
            response["tts"] = self._get_tts_settings(user_id)

            # 4. Get Chat History (limit 50)
            response["chat_history"] = self._get_chat_history(user_id, db_user, limit=50)

            logger.info(f"[DASHBOARD] Init data loaded for user {user_id}")
            return response

        except Exception:
            logger.exception("[ERROR] [DASHBOARD] Error loading init data")
            # Re-raise or return error dict? API usually handles exceptions.
            # But here we want to return a structured error response if possible, 
            # or strictly raise exception for API layer to catch.
            # Given the previous API forwarded 500, we'll raise.
            raise

    async def _get_integrations(self, user_id: int, db_user: User) -> Dict[str, Any]:
        """Get user integration statuses."""
        integrations = {}
        try:
            user_tokens = self.token_repo.get_all_by_user(user_id)
            
            for token in user_tokens:
                if token.access_token:
                    # Validate token (external call)
                    is_valid = await validate_platform_token(token)
                    
                    if is_valid:
                        platform = token.platform
                        username = None
                        
                        if platform == "twitch":
                            username = db_user.twitch_username
                        elif platform == "vk":
                            username = db_user.vk_username
                        elif platform == "donationalerts":
                            username = getattr(db_user, 'donationalerts_username', None)
                        
                        integrations[platform] = {
                            "connected": True,
                            "enabled": True,
                            "username": username,
                            "platform_user_id": token.platform_user_id,
                            "avatar_url": token.avatar_url
                        }
        except Exception:
            logger.exception("[ERROR] [DASHBOARD] Error getting integrations")
        
        return integrations

    def _get_tts_settings(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get concatenated TTS and Audio settings."""
        try:
            tts_settings = self.tts_repo.get_by_user_id(user_id)
            
            if not tts_settings:
                return {
                    "enabled": False,
                    "enabled_platforms": [],
                    "global_enabled": False
                }
            
            audio_settings = self.audio_repo.get_by_user_id(user_id)
            volume = 50
            if audio_settings and hasattr(audio_settings, 'volume'):
                volume = audio_settings.volume
            
            # Construct the specific dictionary format expected by frontend
            return {
                "enabled": tts_settings.enabled if hasattr(tts_settings, 'enabled') else False,
                "enabled_platforms": tts_settings.enabled_platforms if hasattr(tts_settings, 'enabled_platforms') else [],
                "global_enabled": tts_settings.global_enabled if hasattr(tts_settings, 'global_enabled') else False,
                "volume": volume,
                "voice_id": tts_settings.voice_id if hasattr(tts_settings, 'voice_id') else None
            }
        except Exception:
            logger.exception("[ERROR] [DASHBOARD] Error getting TTS settings")
            return None

    def _get_chat_history(self, user_id: int, db_user: User, limit: int = 50) -> List[Dict[str, Any]]:
        """Get formatted chat history."""
        try:
            # Determine channel name
            channel = db_user.twitch_username or db_user.vk_username
            if not channel:
                return []
            
            # Repository call
            messages = self.chat_repo.get_by_channel(
                user_id=user_id,
                channel_name=channel,
                limit=limit,
                include_deleted=False
            )
            
            # Format logic
            messages_data = []
            # 'messages' are ordered DESC (newest first). 
            # Frontend usually expects chronological order or handles it.
            # Original API reversed them: `for msg in reversed(messages):` (so oldest first).
            
            for msg in reversed(messages):
                badges_list = getattr(msg, 'badges', None)
                if isinstance(badges_list, str):
                    try:
                        badges_list = json.loads(badges_list)
                    except Exception:
                        badges_list = None
                
                messages_data.append({
                    "id": msg.id,
                    "author": getattr(msg, 'author_username', None) or 'unknown',
                    "author_name": getattr(msg, 'author_username', None) or 'unknown',
                    "content": msg.message,
                    "message": msg.message,
                    "platform": msg.platform,
                    "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
                    "channel": msg.channel_name,
                    "role": getattr(msg, 'role', None),
                    "badges": badges_list
                })
            
            return messages_data
        except Exception:
            logger.exception("[ERROR] [DASHBOARD] Error getting chat history")
            return []
