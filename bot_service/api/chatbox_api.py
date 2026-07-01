# api/chatbox_api.py
"""
API for ChatBox widget settings used by OBS.
Clean Architecture: uses ChatBoxRepository for data access.
"""
import logging
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, ConfigDict
from core.database import get_db
from auth.auth import get_current_user
from repositories.chatbox_repository import ChatBoxRepository
from repositories.user_token_repository import UserTokenRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chatbox", tags=["chatbox"])


# Pydantic models for the API.
class ChatBoxSettingsCreate(BaseModel):
    """Model for creating or updating ChatBox settings."""
    # Font settings
    font_family: str = Field(default='Tektur')
    font_size: int = Field(default=16, ge=8, le=32)
    font_weight: str = Field(default='normal')
    text_stroke_width: int = Field(default=0, ge=0, le=3)
    text_stroke_color: str = Field(default='#000000')

    # Background
    background_color: str = Field(default='#000000')
    background_opacity: float = Field(default=0.5, ge=0.0, le=1.0)

    # Visibility options
    max_messages: int = Field(default=20, ge=1, le=50)
    show_platform_icons: bool = Field(default=True)
    show_roles: bool = Field(default=False)
    show_badges: bool = Field(default=True)

    # Text colors
    text_color: str = Field(default='#FFFFFF')
    username_color: str = Field(default='#9147FF')

    # Additional settings
    message_spacing: int = Field(default=8, ge=0, le=32)
    border_radius: int = Field(default=8, ge=0, le=32)
    animation_duration: int = Field(default=300, ge=0, le=2000)
    animation_type: str = Field(default='fade')
    chat_direction: str = Field(default='vertical')
    chat_width: int = Field(default=100, ge=20, le=100)
    message_fade_seconds: int = Field(default=60, ge=10, le=60)

    # v0.03 - 7TV, links, images
    show_7tv_emotes: bool = Field(default=True)
    show_links: bool = Field(default=True)
    auto_load_images: bool = Field(default=True)
    separate_message_backgrounds: bool = Field(default=True)
    message_background_mode: Literal['message', 'column', 'none'] = Field(default='message')

    # Version field used to guard against race conditions
    version: int = Field(default=1, ge=1)


class ChatBoxSettingsResponse(ChatBoxSettingsCreate):
    """Response model with ChatBox settings."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    widget_token: str
    widget_url: str


def _settings_to_response(settings, widget_url: str) -> ChatBoxSettingsResponse:
    """Convert settings model to response."""
    message_background_mode = (
        settings.message_background_mode
        if getattr(settings, "message_background_mode", None) in {"message", "column", "none"}
        else ("message" if getattr(settings, "separate_message_backgrounds", True) else "none")
    )
    return ChatBoxSettingsResponse(
        id=settings.id,
        user_id=settings.user_id,
        widget_token=settings.widget_token,
        widget_url=widget_url,
        font_family=settings.font_family,
        font_size=settings.font_size,
        font_weight=settings.font_weight,
        text_stroke_width=settings.text_stroke_width or 0,
        text_stroke_color=settings.text_stroke_color or '#000000',
        background_color=settings.background_color,
        background_opacity=settings.background_opacity,
        max_messages=settings.max_messages,
        show_platform_icons=settings.show_platform_icons,
        show_roles=settings.show_roles,
        show_badges=settings.show_badges,
        text_color=settings.text_color,
        username_color=settings.username_color,
        message_spacing=settings.message_spacing,
        border_radius=settings.border_radius,
        animation_duration=settings.animation_duration,
        animation_type=settings.animation_type,
        chat_direction=settings.chat_direction,
        chat_width=settings.chat_width,
        message_fade_seconds=settings.message_fade_seconds,
        show_7tv_emotes=settings.show_7tv_emotes,
        show_links=settings.show_links,
        auto_load_images=settings.auto_load_images,
        separate_message_backgrounds=message_background_mode == 'message',
        message_background_mode=message_background_mode,
        version=settings.version if hasattr(settings, 'version') else 1
    )


def _get_widget_url(token: str) -> str:
    """Build widget URL from token."""
    from core.config import settings as app_settings
    return f"{app_settings.frontend_url}/chat-overlay?token={token}"


@router.get("/settings", response_model=ChatBoxSettingsResponse)
async def get_chatbox_settings(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the current user's ChatBox settings."""
    user_id = current_user["id"]
    logger.info(f"[CHATBOX] Getting settings for user {user_id}")

    repo = ChatBoxRepository(db)
    settings = repo.get_or_create(user_id)
    
    widget_url = _get_widget_url(settings.widget_token)
    response = _settings_to_response(settings, widget_url)

    logger.info(f"[CHATBOX] Settings retrieved for user {user_id}")
    return response


@router.post("/settings", response_model=ChatBoxSettingsResponse)
async def save_chatbox_settings(
    settings_data: ChatBoxSettingsCreate,
    regenerate_token: bool = False,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Save ChatBox settings and optionally regenerate the token."""
    user_id = current_user["id"]
    logger.info(f"[CHATBOX] Saving settings for user {user_id}, regenerate_token={regenerate_token}")

    repo = ChatBoxRepository(db)
    payload = settings_data.model_dump()
    mode = payload.get("message_background_mode")
    if mode not in {"message", "column", "none"}:
        mode = "message" if payload.get("separate_message_backgrounds", True) else "none"
    payload["message_background_mode"] = mode
    payload["separate_message_backgrounds"] = mode == "message"
    
    try:
        settings = repo.update_settings(
            user_id=user_id,
            settings_data=payload,
            client_version=settings_data.version,
            regenerate_token=regenerate_token
        )
    except ValueError as e:
        # Version conflict
        logger.warning(f"Version conflict for user {user_id}: {e}")
        raise HTTPException(status_code=409, detail="Version conflict")

    widget_url = _get_widget_url(settings.widget_token)
    response = _settings_to_response(settings, widget_url)

    logger.info(f"[CHATBOX] Settings saved for user {user_id}")

    # WebSocket event for real-time update
    from services.memory_websocket_manager import get_memory_websocket_manager

    settings_update_event = {
        "type": "chatbox_settings_updated",
        "data": {
            "font_family": settings.font_family,
            "font_size": settings.font_size,
            "font_weight": settings.font_weight,
            "background_color": settings.background_color,
            "background_opacity": settings.background_opacity,
            "max_messages": settings.max_messages,
            "show_platform_icons": settings.show_platform_icons,
            "show_roles": settings.show_roles,
            "show_badges": settings.show_badges,
            "text_color": settings.text_color,
            "text_stroke_width": settings.text_stroke_width,
            "text_stroke_color": settings.text_stroke_color,
            "username_color": settings.username_color,
            "message_spacing": settings.message_spacing,
            "border_radius": settings.border_radius,
            "animation_duration": settings.animation_duration,
            "animation_type": settings.animation_type,
            "chat_direction": settings.chat_direction,
            "chat_width": settings.chat_width,
            "message_fade_seconds": settings.message_fade_seconds,
            "show_7tv_emotes": settings.show_7tv_emotes,
            "show_links": settings.show_links,
            "auto_load_images": settings.auto_load_images,
            "separate_message_backgrounds": settings.separate_message_backgrounds,
            "message_background_mode": settings.message_background_mode,
        }
    }

    await get_memory_websocket_manager().send_to_user(user_id, settings_update_event)
    logger.info(f"[CHATBOX] Sent settings update event to user {user_id}")

    return response


@router.get("/settings/by-token/{token}")
async def get_settings_by_token(
    token: str,
    db: Session = Depends(get_db)
):
    """Get ChatBox settings by token for the OBS widget without authentication."""
    logger.info(f"[CHATBOX] Getting settings by token: {token[:8]}...")

    repo = ChatBoxRepository(db)
    settings = repo.get_by_token(token)

    if not settings:
        logger.warning(f"[CHATBOX] Settings not found for token: {token[:8]}...")
        raise HTTPException(status_code=404, detail="ChatBox settings not found for this token")

    logger.info(f"[CHATBOX] Settings found for user {settings.user_id}")
    
    channel_name = repo.get_user_channel_name(settings.user_id)
    twitch_token = UserTokenRepository(db).get_active_token(settings.user_id, "twitch")
    twitch_user_id = twitch_token.platform_user_id if twitch_token else None

    return {
        "message_background_mode": (
            settings.message_background_mode
            if getattr(settings, "message_background_mode", None) in {"message", "column", "none"}
            else ("message" if settings.separate_message_backgrounds else "none")
        ),
        "user_id": settings.user_id,
        "channel_name": channel_name,
        "twitch_user_id": twitch_user_id,
        "font_family": settings.font_family,
        "font_size": settings.font_size,
        "font_weight": settings.font_weight,
        "text_stroke_width": settings.text_stroke_width or 0,
        "text_stroke_color": settings.text_stroke_color or '#000000',
        "background_color": settings.background_color,
        "background_opacity": settings.background_opacity,
        "max_messages": settings.max_messages,
        "show_platform_icons": settings.show_platform_icons,
        "show_roles": settings.show_roles,
        "show_badges": settings.show_badges,
        "text_color": settings.text_color,
        "username_color": settings.username_color,
        "message_spacing": settings.message_spacing,
        "border_radius": settings.border_radius,
        "animation_duration": settings.animation_duration,
        "animation_type": settings.animation_type,
        "chat_direction": settings.chat_direction,
        "chat_width": settings.chat_width,
        "message_fade_seconds": settings.message_fade_seconds,
        "show_7tv_emotes": settings.show_7tv_emotes,
        "show_links": settings.show_links,
        "auto_load_images": settings.auto_load_images,
        "separate_message_backgrounds": settings.separate_message_backgrounds,
        "version": settings.version if hasattr(settings, 'version') else 1
    }



