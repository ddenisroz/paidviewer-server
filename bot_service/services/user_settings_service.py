# bot_service/services/user_settings_service.py
"""
Service for managing user interface settings.
Handles authenticated user settings and related cache invalidation.
"""
import logging
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from core.datetime_utils import utcnow_naive
from models.user import UserSettings
from repositories.user_settings_repository import UserSettingsRepository
from services.user_identity_service import UserIdentityService

logger = logging.getLogger('bot_service')


class UserSettingsService:
    """
    Service for UserSettings management.
    Uses UserIdentityService for user validation and identification.
    """

    def __init__(self, repo: Optional[UserSettingsRepository] = None):
        self._repo = repo

    def _get_repo(self, db: Session) -> UserSettingsRepository:
        """Get repository instance."""
        if self._repo:
            return self._repo
        return UserSettingsRepository(db)

    def get_settings(self, user: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """
        Get all settings for user.
        Creates default settings if not exists.
        """
        repo = self._get_repo(db)
        
        # Validate user
        if not UserIdentityService.validate_user_data(user):
            raise ValueError("Invalid user data")

        # Get filters
        filters = UserIdentityService.get_database_filters(user)
        UserIdentityService.log_user_operation("get_user_settings", user)

        # Find or create
        settings = repo.get_by_filters(filters)
        
        if not settings:
            create_data = UserIdentityService.create_settings_record_data(user)
            settings = repo.create_default(create_data)

        return {
            "success": True,
            "settings": self._map_to_dict(settings)
        }

    async def update_settings(
        self,
        user: Dict[str, Any],
        update_data: Dict[str, Any],
        db: Session
    ) -> Dict[str, Any]:
        """
        Update user settings and notify frontend via WebSocket.
        """
        repo = self._get_repo(db)

        # Validate user
        if not UserIdentityService.validate_user_data(user):
            raise ValueError("Invalid user data")

        filters = UserIdentityService.get_database_filters(user)
        UserIdentityService.log_user_operation("update_user_settings", user)

        # Find or create
        settings = repo.get_by_filters(filters)
        if not settings:
            create_data = UserIdentityService.create_settings_record_data(user)
            settings = repo.create_default(create_data)

        # Update
        repo.update(settings, update_data)
        
        # Log update
        user_identifier = UserIdentityService.get_user_identifier(user)
        logger.info(f"User {user_identifier} updated settings: {list(update_data.keys())}")

        # Send WebSocket notification
        # Import here to avoid circular dependencies
        await self._send_cache_invalidation(user)

        return {
            "success": True,
            "message": "Settings saved successfully.",
            "updated_fields": list(update_data.keys()),
            "settings": self._map_to_dict(settings)
        }

    def get_chat_settings(self, user: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """Get only chat settings."""
        settings_response = self.get_settings(user, db)
        full_settings = settings_response["settings"]
        
        return {
            "success": True,
            "chat_settings": {k: v for k, v in full_settings.items() if k.startswith("chat_")}
        }

    def get_obs_settings(self, user: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """Get only OBS settings."""
        settings_response = self.get_settings(user, db)
        full_settings = settings_response["settings"]
        
        # Filter keys: obs_*, and legacy keys without prefix if they exist in map
        obs_settings = {}
        for k, v in full_settings.items():
            if k.startswith("obs_"):
                # Remove prefix for OBS specific response if needed, 
                # but API previously returned with prefix in map, but sub-object keys were without prefix?
                # Let's check API.
                # API returned keys like "width", "height" inside "obs_settings" object, mapped from settings.obs_width
                
                # We need to map back to short keys for OBS endpoint
                short_key = k.replace("obs_", "")
                if k == "obs_text_color": short_key = "text_color" # just to be safe
                obs_settings[short_key] = v
                
        # Colors that might not match exact replace pattern
        # Just map from full_settings for safety
        
        return {
            "success": True,
            "obs_settings": {
                "width": full_settings.get("obs_width"),
                "height": full_settings.get("obs_height"),
                "font_size": full_settings.get("obs_font_size"),
                "font_family": full_settings.get("obs_font_family"),
                "font_weight": full_settings.get("obs_font_weight"),
                "background_color": full_settings.get("obs_background_color"),
                "background_image": full_settings.get("obs_background_image"),
                "text_color": full_settings.get("obs_text_color"),
                "border_radius": full_settings.get("obs_border_radius"),
                "border_color": full_settings.get("obs_border_color"),
                "border_width": full_settings.get("obs_border_width"),
                "message_bg": full_settings.get("obs_message_bg"),
                "message_border_radius": full_settings.get("obs_message_border_radius"),
                "message_margin": full_settings.get("obs_message_margin"),
                "message_padding": full_settings.get("obs_message_padding"),
                "moderator_color": full_settings.get("obs_moderator_color"),
                "vip_color": full_settings.get("obs_vip_color"),
                "subscriber_color": full_settings.get("obs_subscriber_color"),
                "normal_color": full_settings.get("obs_normal_color")
            }
        }

    async def _send_cache_invalidation(self, user: Dict[str, Any]):
        """Send cache invalidation event via WebSocket."""
        try:
            from services.memory_websocket_manager import get_memory_websocket_manager
            
            user_id = user.get("id")
            # Cache invalidation is delivered only to authenticated user channels.
            
            if user_id:
                cache_invalidation_event = {
                    "type": "cache_invalidate",
                    "cache_key": "cache_user_settings",
                    "reason": "settings_updated"
                }
                await get_memory_websocket_manager().send_to_user(user_id, cache_invalidation_event)
                logger.debug(f"[REFRESH] [USER_SETTINGS] Sent cache invalidation to user {user_id}")
                
        except Exception:
            logger.exception("Error sending cache invalidation")

    def _map_to_dict(self, settings: UserSettings) -> Dict[str, Any]:
        """Map UserSettings model to dictionary."""
        return {
            # Chat settings
            "chat_enabled": settings.chat_enabled,
            "chat_max_messages": settings.chat_max_messages,
            "chat_show_timestamps": settings.chat_show_timestamps,
            "chat_show_platform": settings.chat_show_platform,
            "chat_show_user_roles": settings.chat_show_user_roles,
            "chat_animation_duration": settings.chat_animation_duration,
            "chat_animation_type": settings.chat_animation_type,

            # OBS chat settings
            "obs_width": settings.obs_width,
            "obs_height": settings.obs_height,
            "obs_font_size": settings.obs_font_size,
            "obs_font_family": settings.obs_font_family,
            "obs_font_weight": settings.obs_font_weight,
            "obs_background_color": settings.obs_background_color,
            "obs_background_image": settings.obs_background_image,
            "obs_text_color": settings.obs_text_color,
            "obs_border_radius": settings.obs_border_radius,
            "obs_border_color": settings.obs_border_color,
            "obs_border_width": settings.obs_border_width,
            "obs_message_bg": settings.obs_message_bg,
            "obs_message_border_radius": settings.obs_message_border_radius,
            "obs_message_margin": settings.obs_message_margin,
            "obs_message_padding": settings.obs_message_padding,

            # OBS role colors
            "obs_moderator_color": settings.obs_moderator_color,
            "obs_vip_color": settings.obs_vip_color,
            "obs_subscriber_color": settings.obs_subscriber_color,
            "obs_normal_color": settings.obs_normal_color,

            # Field merge settings
            "combine_titles": settings.combine_titles,
            "combine_categories": settings.combine_categories,
        }

