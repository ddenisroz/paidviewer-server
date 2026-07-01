# bot_service/api/youtube/settings_routes.py
"""API endpoints for YouTube integration settings."""

import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.auth import get_current_user
from core.database import get_db
from repositories.tts_settings_repository import TTSSettingsRepository
from repositories.user_token_repository import UserTokenRepository
from core.connection_manager import get_connection_manager
from services.youtube.obs_overlay import build_youtube_obs_state
from services.youtube.reward_settings import (
    apply_youtube_settings_update,
    build_youtube_settings_response,
)

logger = logging.getLogger('bot_service')

youtube_settings_router = APIRouter(prefix="/api/tts", tags=["youtube-settings"])


class YouTubeSettingsResponse(BaseModel):
    """Response model for YouTube settings."""

    playback_mode: Literal['browser', 'obs'] = Field(default='browser', description='Playback mode')
    obs_overlay_mode: Literal['video', 'track'] = Field(default='track', description='OBS overlay display mode')
    volume_level: int = Field(default=100, ge=0, le=100, description='Volume level (0-100)')
    requests_command_enabled: bool = Field(default=True, description='Allow !sr command')
    request_command_name: str = Field(default='!sr', description='Viewer command for video requests')

    # Legacy single-platform reward settings (kept for backward compatibility)
    requests_reward_enabled: bool = Field(default=False, description='Allow reward-based requests')
    requests_reward_id: Optional[str] = Field(None, description='Legacy reward identifier')
    requests_reward_platform: Literal['twitch', 'vk'] = Field(default='twitch', description='Legacy reward platform')

    # New per-platform reward settings
    requests_reward_twitch_enabled: bool = Field(default=False, description='Allow Twitch reward requests')
    requests_reward_twitch_id: Optional[str] = Field(None, description='Twitch reward ID')
    requests_reward_vk_enabled: bool = Field(default=False, description='Allow VK reward requests')
    requests_reward_vk_id: Optional[str] = Field(None, description='VK reward title')
    paid_orders_enabled: bool = Field(default=False, description='Allow paid video orders')
    paid_order_mode: Literal['rub_per_minute', 'full_video'] = Field(default='rub_per_minute', description='Paid order tariff mode')
    paid_order_rate_rub_per_minute: float = Field(default=0, ge=0, description='RUB per minute paid video tariff')
    paid_order_min_amount_rub: float = Field(default=0, ge=0, description='Minimum RUB donation for full-video paid order')
    paid_order_priority_by_amount: bool = Field(default=True, description='Sort paid donation orders by amount')
    donationalerts_video_enabled: bool = Field(default=False, description='Allow DonationAlerts paid video links')
    donationalerts_video_min_amount: float = Field(default=0, ge=0, description='Minimum DonationAlerts amount for paid video')
    donationalerts_video_priority_next: bool = Field(default=True, description='Put paid videos into the next slot')


class YouTubeSettingsUpdate(BaseModel):
    """Request model for updating YouTube settings."""

    playback_mode: Optional[Literal['browser', 'obs']] = Field(None, description='Playback mode')
    obs_overlay_mode: Optional[Literal['video', 'track']] = Field(None, description='OBS overlay display mode')
    volume_level: Optional[int] = Field(None, ge=0, le=100, description='Volume level (0-100)')
    requests_command_enabled: Optional[bool] = Field(None, description='Allow !sr command')
    request_command_name: Optional[str] = Field(None, min_length=1, max_length=32, description='Viewer command for video requests')

    # Legacy single-platform reward settings (accepted for compatibility)
    requests_reward_enabled: Optional[bool] = Field(None, description='Allow reward-based requests')
    requests_reward_id: Optional[str] = Field(None, description='Legacy reward identifier')
    requests_reward_platform: Optional[Literal['twitch', 'vk']] = Field(None, description='Legacy reward platform')

    # New per-platform reward settings
    requests_reward_twitch_enabled: Optional[bool] = Field(None, description='Allow Twitch reward requests')
    requests_reward_twitch_id: Optional[str] = Field(None, description='Twitch reward ID')
    requests_reward_vk_enabled: Optional[bool] = Field(None, description='Allow VK reward requests')
    requests_reward_vk_id: Optional[str] = Field(None, description='VK reward title')
    paid_orders_enabled: Optional[bool] = Field(None, description='Allow paid video orders')
    paid_order_mode: Optional[Literal['rub_per_minute', 'full_video']] = Field(None, description='Paid order tariff mode')
    paid_order_rate_rub_per_minute: Optional[float] = Field(None, ge=0, description='RUB per minute paid video tariff')
    paid_order_min_amount_rub: Optional[float] = Field(None, ge=0, description='Minimum RUB donation for full-video paid order')
    paid_order_priority_by_amount: Optional[bool] = Field(None, description='Sort paid donation orders by amount')
    donationalerts_video_enabled: Optional[bool] = Field(None, description='Allow DonationAlerts paid video links')
    donationalerts_video_min_amount: Optional[float] = Field(None, ge=0, description='Minimum DonationAlerts amount for paid video')
    donationalerts_video_priority_next: Optional[bool] = Field(None, description='Put paid videos into the next slot')

def _get_youtube_settings_from_tts(tts_settings) -> dict:
    """Extract and normalize YouTube settings from TTS settings object."""

    youtube_settings = getattr(tts_settings, 'youtube_settings', None) or {}
    return build_youtube_settings_response(youtube_settings)


def _wants_paid_orders(update: YouTubeSettingsUpdate) -> bool:
    """Return True when this update explicitly enables DonationAlerts video orders."""

    return bool(update.paid_orders_enabled is True or update.donationalerts_video_enabled is True)


@youtube_settings_router.get('/youtube-settings', response_model=YouTubeSettingsResponse)
async def get_youtube_settings(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get YouTube settings for current user."""

    try:
        user_id = user.get('id')

        repo = TTSSettingsRepository(db)
        tts_settings = repo.get_or_create(user_id=user_id)
        settings = _get_youtube_settings_from_tts(tts_settings)
        return YouTubeSettingsResponse(**settings)

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting YouTube settings")
        raise HTTPException(status_code=500, detail="Internal server error")


@youtube_settings_router.post('/youtube-settings', response_model=YouTubeSettingsResponse)
async def save_youtube_settings(
    settings: YouTubeSettingsUpdate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save YouTube settings for current user."""

    try:
        user_id = user.get('id')

        repo = TTSSettingsRepository(db)
        tts_settings = repo.get_or_create(user_id=user_id)

        if _wants_paid_orders(settings):
            da_token = UserTokenRepository(db).get_active_token(user_id, "donationalerts")
            if not da_token or not getattr(da_token, "access_token", None):
                raise HTTPException(
                    status_code=400,
                    detail="DonationAlerts integration is required for paid YouTube orders.",
                )

        youtube_settings = apply_youtube_settings_update(
            getattr(tts_settings, 'youtube_settings', None) or {},
            settings.model_dump(exclude_unset=True),
        )

        repo.update_settings(tts_settings, {'youtube_settings': youtube_settings})
        await get_connection_manager().send_youtube_obs_to_user(
            user_id,
            {
                "type": "youtube_obs_state",
                "data": build_youtube_obs_state(user_id, db),
            },
        )
        logger.info("YouTube settings saved for user %s", user_id)
        return YouTubeSettingsResponse(**build_youtube_settings_response(youtube_settings))

    except HTTPException:
        raise
    except Exception:
        db.rollback()
        logger.exception("Error saving YouTube settings")
        raise HTTPException(status_code=500, detail="Internal server error")


@youtube_settings_router.get('/obs-url')
async def get_obs_url(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get OBS URL token for current user."""

    try:
        user_id = user.get('id')

        from repositories.user_repository import UserRepository

        repo = UserRepository(db)
        user_record = repo.get_by_id(user_id)

        if not user_record:
            raise HTTPException(status_code=404, detail="User not found")

        return {
            'obs_token': user_record.obs_token,
            'has_token': user_record.obs_token is not None,
        }

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting OBS URL")
        raise HTTPException(status_code=500, detail="Internal server error")

