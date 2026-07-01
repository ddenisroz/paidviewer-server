"""WebSocket helper wrappers delegated to dedicated services."""

import logging
from typing import Any, Dict, Optional

from services.notification_service import notification_service
from services.tts_handler_service import tts_handler_service

logger = logging.getLogger("bot_service")


async def broadcast_chat_message(
    username: str,
    content: str,
    platform: str,
    channel: str,
    message_id: Optional[str] = None,
    role: Optional[str] = None,
    badges: Optional[list] = None,
    emotes: Optional[list] = None,
    avatar_url: Optional[str] = None,
) -> bool:
    """Broadcast a chat message to all active WebSocket connections."""

    return await notification_service.broadcast_chat_message(
        username,
        content,
        platform,
        channel,
        message_id,
        role,
        badges,
        emotes,
        avatar_url,
    )


async def handle_tts_for_message(
    text: str,
    username: str,
    channel_identifier: str,
    platform: str,
    tts_api,
    connection_manager,
    skip_if_command: bool = True,
    is_reply: bool = False,
    mentioned_users: list = None,
    reward_id: str = None,
    message_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Process a chat message through the TTS handler service."""

    return await tts_handler_service.process_message_for_tts(
        text,
        username,
        channel_identifier,
        platform,
        tts_api,
        connection_manager,
        skip_if_command,
        is_reply,
        mentioned_users,
        reward_id,
        message_id,
    )


async def broadcast_tts_audio(audio_data: Dict[str, Any], channel_name: str, platform: str = "twitch") -> bool:
    """Broadcast generated TTS audio to frontend clients."""

    return await notification_service.broadcast_tts_audio(audio_data, channel_name, platform)


async def broadcast_drops_event(drops_data: Dict[str, Any]) -> bool:
    """Broadcast a drops event to subscribed clients."""

    return await notification_service.broadcast_drops_event(drops_data)
