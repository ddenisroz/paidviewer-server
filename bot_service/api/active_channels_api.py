# bot_service/api/active_channels_api.py
"""
API for active channels.
Clean Architecture: uses UserSettingsRepository for data access.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from core.database import get_db
from auth.auth import get_current_user
from repositories.user_settings_repository import UserSettingsRepository
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["channels"])

@router.get("/active-channels")
async def get_active_channels(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the list of active channels."""
    try:
        repo = UserSettingsRepository(db)
        channels = repo.get_with_chat_enabled()

        channels_data = []
        for channel in channels:
            channel_data = {
                'id': channel.id,
                'tts_enabled': getattr(channel, 'tts_enabled', False),
                'created_at': channel.created_at.isoformat() if channel.created_at else None
            }

            # Attach channel details based on the platform.
            if hasattr(channel, 'channel_name') and channel.channel_name:
                channel_data.update({
                    'platform': 'twitch',
                    'channel_name': channel.channel_name
                })
            elif hasattr(channel, 'vk_channel_name') and channel.vk_channel_name:
                channel_data.update({
                    'platform': 'vk',
                    'channel_name': channel.vk_channel_name
                })

            channels_data.append(channel_data)

        return {
            "success": True,
            "channels": channels_data,
            "total": len(channels_data)
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting active channels")
        raise HTTPException(status_code=500, detail="Internal server error")
