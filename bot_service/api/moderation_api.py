# bot_service/api/moderation_api.py
"""API for user moderation (TTS blocking and platform timeouts)"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from auth.auth import get_current_user
from services.moderation_service import moderation_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/moderation", tags=["moderation"])

class ToggleMuteRequest(BaseModel):
    username: str
    platform: str  # 'twitch' or 'vk'
    channel_name: str
    duration_seconds: Optional[int] = 600
    reason: Optional[str] = "Muted by moderator"

class MuteStatusResponse(BaseModel):
    success: bool
    action: str  # 'muted' or 'unmuted'
    username: str
    platform: str
    platform_mute_applied: bool = False
    message: str

@router.post("/toggle-mute", response_model=MuteStatusResponse)
async def toggle_mute_user(
    request: ToggleMuteRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Mute/Unmute user in TTS + Platform Timeout (Twitch).
    """
    try:
        user_id = current_user.get('id')
        if not user_id:
             raise HTTPException(status_code=401, detail="User ID not found")

        result = await moderation_service.toggle_mute(
            user_id=int(user_id),
            username=request.username,
            platform=request.platform,
            channel_name=request.channel_name,
            duration_seconds=request.duration_seconds or 600,
            reason=request.reason or "Muted by moderator"
        )
        
        return MuteStatusResponse(**result)

    except HTTPException:
        raise
    except Exception:
        logger.exception("[MODERATION] Error toggling mute")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/muted-users")
async def get_muted_users(
    platform: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Get list of muted users"""
    try:
        user_id = current_user.get('id')
        if not user_id:
             raise HTTPException(status_code=401, detail="User ID not found")

        blocked_users = moderation_service.get_muted_users(int(user_id), platform)

        return {
            "success": True,
            "blocked_users": [
                {
                    "id": user.id,
                    "username": user.username,
                    "platform": user.platform,
                    "channel_name": user.channel_name,
                    "blocked_at": user.blocked_at.isoformat() if user.blocked_at else None,
                    "reason": user.reason
                }
                for user in blocked_users
            ]
        }

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting muted users")
        raise HTTPException(status_code=500, detail="Internal server error")

# Helper function exposed for other modules if needed (e.g. TTS engine)
def is_user_blocked_from_tts(channel_name: str, platform: str, username: str) -> bool:
    return moderation_service.is_user_blocked_from_tts(channel_name, platform, username)
