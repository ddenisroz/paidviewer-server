# bot_service/api/user/settings.py
"""
User-specific settings endpoints.

Clean Architecture: This module only handles HTTP routing.
All business logic delegated to services.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from core.database import get_db
from auth.auth import get_current_user
from core.permissions import require_permission, Permission, require_ownership_or_admin
from typing import Optional
from pydantic import BaseModel
import logging

from services.user_settings_service import UserSettingsService
from services.tts.tts_service import TTSService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/user/settings", tags=["user-settings"])


# === Pydantic Models ===

class UserSettingsUpdateRequest(BaseModel):
    """Request model for updating user settings"""
    chat_enabled: Optional[bool] = None
    chat_max_messages: Optional[int] = None
    chat_show_timestamps: Optional[bool] = None
    chat_show_platform: Optional[bool] = None
    obs_width: Optional[int] = None
    obs_height: Optional[int] = None
    obs_font_size: Optional[int] = None
    obs_background_color: Optional[str] = None
    obs_text_color: Optional[str] = None


class TTSSettingsUpdateRequest(BaseModel):
    """Request model for updating TTS settings"""
    engine: Optional[str] = None
    advanced_provider: Optional[str] = None
    f5_mode: Optional[str] = None
    voice: Optional[str] = None
    listening_mode: Optional[str] = None
    use_local_tts: Optional[bool] = None
    enabled_platforms: Optional[list] = None
    tts_mode: Optional[str] = None
    gcloud_voices: Optional[list] = None
    gcloud_mood: Optional[str] = None


class AudioSettingsUpdateRequest(BaseModel):
    """Request model for updating audio settings"""
    website_volume: Optional[int] = None
    obs_volume: Optional[int] = None


# === Dependency Injection ===

def get_user_settings_service(db: Session = Depends(get_db)) -> UserSettingsService:
    return UserSettingsService()


def get_tts_service(db: Session = Depends(get_db)) -> TTSService:
    return TTSService(db)


# === Endpoints ===

@router.get("/me")
@require_permission(Permission.MANAGE_OWN_SETTINGS)
async def get_my_settings(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    user_service: UserSettingsService = Depends(get_user_settings_service),
    tts_service: TTSService = Depends(get_tts_service)
):
    """
    Get current user's settings.
    
    Requires: MANAGE_OWN_SETTINGS permission
    """
    try:
        # Get user settings via service
        settings_result = user_service.get_settings(current_user, db)
        
        # Get TTS settings via service
        tts_settings = await tts_service.get_tts_settings(user_id=current_user.get('id'))
        
        # Get audio settings via service
        audio_settings = await tts_service.get_audio_settings(user_id=current_user.get('id'))
        
        return {
            "success": True,
            "settings": settings_result.get("settings", {}),
            "tts_settings": tts_settings,
            "audio_settings": audio_settings
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting user settings")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/me")
@require_permission(Permission.MANAGE_OWN_SETTINGS)
async def update_my_settings(
    request: UserSettingsUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    user_service: UserSettingsService = Depends(get_user_settings_service)
):
    """
    Update current user's settings.
    
    Requires: MANAGE_OWN_SETTINGS permission
    """
    try:
        update_data = request.model_dump(exclude_unset=True)
        result = user_service.update_settings(current_user, update_data, db)
        return result
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid settings data")
    except Exception:
        logger.exception("Error updating user settings")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/me/tts")
@require_permission(Permission.MANAGE_OWN_SETTINGS)
async def update_my_tts_settings(
    request: TTSSettingsUpdateRequest,
    current_user: dict = Depends(get_current_user),
    tts_service: TTSService = Depends(get_tts_service)
):
    """
    Update current user's TTS settings.
    
    Requires: MANAGE_OWN_SETTINGS permission
    """
    try:
        user_id = current_user.get('id')
        
        # Validate inputs
        if request.engine is not None:
            valid_engines = ['gtts', 'f5tts', 'gcloud']
            if request.engine not in valid_engines:
                raise HTTPException(status_code=400, detail=f"Invalid engine. Must be one of: {valid_engines}")

        if request.advanced_provider is not None:
            valid_providers = ['f5', 'gcloud']
            if request.advanced_provider not in valid_providers:
                raise HTTPException(status_code=400, detail=f"Invalid advanced_provider. Must be one of: {valid_providers}")

        if request.f5_mode is not None and request.f5_mode not in {'cloud', 'local'}:
            raise HTTPException(status_code=400, detail="Invalid f5_mode. Must be one of: cloud, local")

        if request.listening_mode is not None:
            valid_modes = ['website', 'obs']
            if request.listening_mode not in valid_modes:
                raise HTTPException(status_code=400, detail=f"Invalid listening mode. Must be one of: {valid_modes}")

        if request.tts_mode is not None:
            valid_modes = ['all_messages', 'channel_points']
            if request.tts_mode not in valid_modes:
                raise HTTPException(status_code=400, detail=f"Invalid TTS mode. Must be one of: {valid_modes}")

        # Update via service
        save_payload = {"user_id": user_id}
        if request.engine is not None:
            save_payload["engine"] = request.engine
        if request.advanced_provider is not None:
            save_payload["advanced_provider"] = request.advanced_provider
        if request.f5_mode is not None:
            save_payload["f5_mode"] = request.f5_mode
        if request.voice is not None:
            save_payload["voice"] = request.voice
        if request.listening_mode is not None:
            save_payload["listening_mode"] = request.listening_mode
        if request.use_local_tts is not None:
            save_payload["use_local_tts"] = request.use_local_tts
        if request.enabled_platforms is not None:
            save_payload["enabled_platforms"] = request.enabled_platforms
        if request.tts_mode is not None:
            save_payload["tts_mode"] = request.tts_mode
        if request.gcloud_voices is not None:
            save_payload["gcloud_voices"] = request.gcloud_voices
        if request.gcloud_mood is not None:
            save_payload["gcloud_mood"] = request.gcloud_mood

        result = await tts_service.save_tts_settings(**save_payload)
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail="Failed to update TTS settings")
        
        return {
            "success": True,
            "message": "TTS settings updated successfully"
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error updating TTS settings")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/me/audio")
@require_permission(Permission.MANAGE_OWN_SETTINGS)
async def update_my_audio_settings(
    request: AudioSettingsUpdateRequest,
    current_user: dict = Depends(get_current_user),
    tts_service: TTSService = Depends(get_tts_service)
):
    """
    Update current user's audio settings.
    
    Requires: MANAGE_OWN_SETTINGS permission
    """
    try:
        user_id = current_user.get('id')
        
        # Validate volume ranges
        if request.website_volume is not None:
            if not 0 <= request.website_volume <= 100:
                raise HTTPException(status_code=400, detail="Website volume must be between 0 and 100")

        if request.obs_volume is not None:
            if not 0 <= request.obs_volume <= 100:
                raise HTTPException(status_code=400, detail="OBS volume must be between 0 and 100")

        # Update via service (website volume)
        if request.website_volume is not None:
            success = await tts_service.save_audio_settings(
                user_id=user_id,
                website_volume=request.website_volume
            )
            if not success:
                raise HTTPException(status_code=500, detail="Failed to save audio settings")

        # Note: obs_volume not currently in TTSService, would need separate handling
        # For now, we only support website_volume through TTSService

        return {
            "success": True,
            "message": "Audio settings updated successfully"
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error updating audio settings")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{user_id}")
@require_ownership_or_admin(resource_user_id_param="user_id")
async def get_user_settings(
    user_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    user_service: UserSettingsService = Depends(get_user_settings_service),
    tts_service: TTSService = Depends(get_tts_service)
):
    """
    Get settings for a specific user.
    
    Requires: Ownership of the resource or admin role
    """
    try:
        # Create user dict for service
        target_user = {"id": user_id}
        
        # Get settings via services
        settings_result = user_service.get_settings(target_user, db)
        tts_settings = await tts_service.get_tts_settings(user_id=user_id)
        audio_settings = await tts_service.get_audio_settings(user_id=user_id)
        
        return {
            "success": True,
            "settings": settings_result.get("settings", {}),
            "tts_settings": tts_settings,
            "audio_settings": audio_settings
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting user settings")
        raise HTTPException(status_code=500, detail="Internal server error")



