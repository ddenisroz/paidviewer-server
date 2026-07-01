"""
WebSocket Broadcast Utilities

Helper functions for broadcasting state changes via WebSocket.
Uses MemoryWebSocketManager for correct message delivery.
"""
import logging
from typing import Dict, Any
from services.memory_websocket_manager import get_memory_websocket_manager

logger = logging.getLogger(__name__)

async def broadcast_settings_change(user_id: int, setting_type: str, settings: Dict[str, Any]):
    """
    Broadcast settings change to all user's connections
    
    Args:
        user_id: User ID
        setting_type: Type of settings (e.g., 'settings', 'tts_settings')
        settings: Updated settings data
    """
    try:
        manager = get_memory_websocket_manager()
        message = {
            "type": f"{setting_type}_updated",
            "data": {
                "settings": settings
            }
        }
        await manager.send_to_user(user_id, message)
        logger.debug(f"Broadcasted {setting_type} change for user {user_id}")
    except Exception as e:
        logger.error(f"Error broadcasting settings change: {e}")


async def broadcast_stream_info_change(user_id: int, platform: str, stream_info: Dict[str, Any]):
    """
    Broadcast stream info change to all user's connections
    
    Args:
        user_id: User ID
        platform: Platform name ('twitch' or 'vk')
        stream_info: Updated stream information
    """
    try:
        manager = get_memory_websocket_manager()
        message = {
            "type": "stream_info_updated",
            "data": {
                "platform": platform,
                "stream_info": stream_info
            }
        }
        await manager.send_to_user(user_id, message)
        logger.debug(f"Broadcasted stream info change for user {user_id} on {platform}")
    except Exception as e:
        logger.error(f"Error broadcasting stream info change: {e}")


async def broadcast_tts_status_change(user_id: int, enabled: bool):
    """
    Broadcast TTS status change to all user's connections
    
    Args:
        user_id: User ID
        enabled: Whether TTS is enabled
    """
    try:
        manager = get_memory_websocket_manager()
        message = {
            "type": "tts_status_changed",
            "data": {
                "enabled": enabled
            }
        }
        await manager.send_to_user(user_id, message)
        logger.debug(f"Broadcasted TTS status change for user {user_id}: {enabled}")
    except Exception as e:
        logger.error(f"Error broadcasting TTS status change: {e}")


async def broadcast_youtube_queue_update(user_id: int):
    """
    Broadcast YouTube queue update to all user's connections
    
    Args:
        user_id: User ID
    """
    try:
        manager = get_memory_websocket_manager()
        message = {
            "type": "youtube_queue_updated",
            "data": {}
        }
        await manager.send_to_user(user_id, message)
        try:
            from core.connection_manager import get_connection_manager

            await get_connection_manager().send_youtube_obs_to_user(user_id, message)
        except Exception:
            logger.debug("YouTube OBS queue signal broadcast failed", exc_info=True)
        logger.debug(f"Broadcasted YouTube queue update for user {user_id}")
    except Exception as e:
        logger.error(f"Error broadcasting YouTube queue update: {e}")


async def broadcast_points_update(user_id: int):
    """
    Broadcast points/rewards update to all user's connections
    
    Args:
        user_id: User ID
    """
    try:
        manager = get_memory_websocket_manager()
        message = {
            "type": "points_updated",
            "data": {}
        }
        await manager.send_to_user(user_id, message)
        logger.debug(f"Broadcasted points update for user {user_id}")
    except Exception as e:
        logger.error(f"Error broadcasting points update: {e}")


async def broadcast_drops_result(user_id: int, result: Dict[str, Any]):
    """
    Broadcast drops result to all user's connections
    
    Args:
        user_id: User ID
        result: Drops result data
    """
    try:
        manager = get_memory_websocket_manager()
        message = {
            "type": "drops_result",
            "data": result
        }
        await manager.send_to_user(user_id, message)
        logger.debug(f"Broadcasted drops result for user {user_id}")
    except Exception as e:
        logger.error(f"Error broadcasting drops result: {e}")
