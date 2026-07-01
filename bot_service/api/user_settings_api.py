# api/user_settings_api.py
"""
API for user interface settings management.
Following Clean Architecture: routing only, no business logic.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.auth import get_current_user
from core.database import get_db
from services.user_settings_service import UserSettingsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/user-settings", tags=["user-settings"])


class UserSettingsUpdate(BaseModel):
    """Model for updating user interface settings."""

    chat_enabled: Optional[bool] = None
    chat_max_messages: Optional[int] = Field(None, ge=1, le=1000)
    chat_show_timestamps: Optional[bool] = None
    chat_show_platform: Optional[bool] = None
    chat_show_user_roles: Optional[bool] = None
    chat_animation_duration: Optional[int] = Field(None, ge=100, le=5000)
    chat_animation_type: Optional[str] = Field(None, pattern="^(slide|fade|none)$")

    obs_width: Optional[int] = Field(None, ge=100, le=2000)
    obs_height: Optional[int] = Field(None, ge=100, le=2000)
    obs_font_size: Optional[int] = Field(None, ge=8, le=72)
    obs_font_family: Optional[str] = None
    obs_font_weight: Optional[str] = Field(None, pattern="^(normal|bold|light)$")
    obs_background_color: Optional[str] = Field(None, pattern="^#[0-9a-fA-F]{6}$")
    obs_background_image: Optional[str] = None
    obs_text_color: Optional[str] = Field(None, pattern="^#[0-9a-fA-F]{6}$")
    obs_border_radius: Optional[int] = Field(None, ge=0, le=50)
    obs_border_color: Optional[str] = Field(None, pattern="^#[0-9a-fA-F]{6}$")
    obs_border_width: Optional[int] = Field(None, ge=0, le=20)
    obs_message_bg: Optional[str] = Field(None, pattern="^#[0-9a-fA-F]{6}$")
    obs_message_border_radius: Optional[int] = Field(None, ge=0, le=50)
    obs_message_margin: Optional[int] = Field(None, ge=0, le=20)
    obs_message_padding: Optional[int] = Field(None, ge=0, le=50)

    obs_moderator_color: Optional[str] = Field(None, pattern="^#[0-9a-fA-F]{6}$")
    obs_vip_color: Optional[str] = Field(None, pattern="^#[0-9a-fA-F]{6}$")
    obs_subscriber_color: Optional[str] = Field(None, pattern="^#[0-9a-fA-F]{6}$")
    obs_normal_color: Optional[str] = Field(None, pattern="^#[0-9a-fA-F]{6}$")

    combine_titles: Optional[bool] = None
    combine_categories: Optional[bool] = None


def get_settings_service() -> UserSettingsService:
    """Get UserSettingsService instance."""
    return UserSettingsService()


@router.get("/")
async def get_user_settings(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all user settings."""
    try:
        service = get_settings_service()
        return service.get_settings(current_user, db)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid settings data")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting user settings")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/")
async def update_user_settings(
    settings_update: UserSettingsUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update user settings."""
    try:
        service = get_settings_service()
        return await service.update_settings(
            user=current_user,
            update_data=settings_update.model_dump(exclude_unset=True),
            db=db,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid settings data")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error updating user settings")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/chat")
async def get_chat_settings(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get chat settings."""
    try:
        service = get_settings_service()
        return service.get_chat_settings(current_user, db)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid settings data")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting chat settings")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/obs")
async def get_obs_settings(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get OBS settings."""
    try:
        service = get_settings_service()
        return service.get_obs_settings(current_user, db)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid settings data")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting OBS settings")
        raise HTTPException(status_code=500, detail="Internal server error")
