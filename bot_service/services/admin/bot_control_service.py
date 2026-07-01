# bot_service/services/admin/bot_control_service.py
"""
Service for bot status and restart operations.
"""

import logging

import httpx

from core.datetime_utils import utcnow_naive
from core.internal_service_auth import build_tts_auth_headers, build_tts_httpx_client_kwargs
from core.connection_manager import get_connection_manager
from core.database import get_db
from startup.bot_registry import get_bot_registry
from services.tts.provider_utils import get_provider_service_url

logger = logging.getLogger(__name__)


class BotControlService:
    """Service for managing bots."""

    async def get_bots_status(self) -> dict:
        """Get the status of all bots."""
        try:
            registry = get_bot_registry()
            connection_manager = get_connection_manager()
            bots = []

            # Twitch bot status
            twitch_status = "stopped"
            twitch_channels = 0

            if registry.is_twitch_running():
                twitch_status = "running"
                if registry.twitch_bot and hasattr(registry.twitch_bot, 'connected_channels'):
                    twitch_channels = len(registry.twitch_bot.connected_channels)

            bots.append({
                "name": "twitch_bot",
                "status": twitch_status,
                "last_activity": utcnow_naive().isoformat(),
                "platform": "twitch",
                "connected_channels": twitch_channels
            })

            # VK Live bot status
            vk_status = "stopped"
            vk_channels = 0

            if registry.is_vk_running():
                vk_status = "running"
                if hasattr(connection_manager, 'active_vk_bots'):
                    vk_channels = len(connection_manager.active_vk_bots)

            bots.append({
                "name": "vk_live_bot",
                "status": vk_status,
                "last_activity": utcnow_naive().isoformat(),
                "platform": "vk_live",
                "connected_channels": vk_channels
            })

            return {"bots": bots}

        except Exception:
            logger.exception("Error getting bots status")
            return {
                "bots": [
                    {
                        "name": "twitch_bot",
                        "status": "error",
                        "last_activity": utcnow_naive().isoformat(),
                        "platform": "twitch",
                        "connected_channels": 0
                    },
                    {
                        "name": "vk_live_bot",
                        "status": "error",
                        "last_activity": utcnow_naive().isoformat(),
                        "platform": "vk_live",
                        "connected_channels": 0
                    }
                ]
            }

    async def restart_bot(self, bot_name: str) -> dict:
        """Restart a bot."""
        try:
            registry = get_bot_registry()
            connection_manager = get_connection_manager()

            if bot_name == "twitch_bot":
                return await self._restart_twitch_bot(registry, connection_manager)
            elif bot_name == "vk_live_bot":
                return await self._restart_vk_bot(registry, connection_manager)
            else:
                return {"error": f"Unknown bot: {bot_name}"}

        except Exception:
            logger.exception("Error restarting bot {bot_name}")
            return {"error": "Failed to restart bot"}

    async def _restart_twitch_bot(self, registry, connection_manager) -> dict:
        """Restart the Twitch bot."""
        logger.info("[REFRESH] Restarting Twitch bot...")

        # Stop the current bot instance.
        await registry.stop_twitch_bot()

        # Load active channels.
        db = next(get_db())
        try:
            active_channels = await connection_manager.get_twitch_channels_for_bot(db)
        finally:
            db.close()
        from startup.bot_initializer import initialize_twitch_bot

        success = await initialize_twitch_bot(active_channels)
        if not success:
            return {"error": "Twitch bot OAuth token not configured. Use /auth/twitch/bot/login"}

        logger.info(f"[OK] Twitch bot restarted with channels: {active_channels}")
        return {
            "message": "Twitch bot restarted successfully",
            "channels": active_channels
        }

    async def _restart_vk_bot(self, registry, connection_manager) -> dict:
        """Restart the VK Live bot."""
        logger.info("[REFRESH] Restarting VK Live bot...")

        # Stop the current bot instance.
        await registry.stop_vk_bot()

        # Load active channels.
        db = next(get_db())
        try:
            active_channels = await connection_manager.get_vk_channels_for_bot(db)
        finally:
            db.close()
        from startup.bot_initializer import initialize_vk_bot

        success = await initialize_vk_bot(active_channels)
        if not success:
            return {"error": "VK bot OAuth token not configured. Use /auth/vk/bot/login"}

        # Reconnect to channels.

        logger.info(f"[OK] VK Live bot restarted with channels: {active_channels}")
        return {
            "message": "VK Live bot restarted successfully",
            "channels": active_channels
        }

    async def restart_tts_engine(self) -> dict:
        """Reload the TTS engine."""
        try:
            tts_service_url = get_provider_service_url("f5")
            if not tts_service_url:
                raise ValueError("F5_TTS_SERVICE_URL is not configured")

            async with httpx.AsyncClient(timeout=30.0, **build_tts_httpx_client_kwargs()) as client:
                headers = build_tts_auth_headers()
                response = await client.post(f"{tts_service_url}/api/tts/restart", headers=headers)

                if response.status_code == 200:
                    logger.info("[OK] TTS engine restart requested")
                    return {"message": "TTS engine restart requested successfully"}
                else:
                    logger.error(f"[ERROR] TTS restart failed: {response.status_code}")
                    return {"error": f"TTS engine restart failed: {response.status_code}"}

        except Exception:
            logger.exception("Error restarting TTS engine")
            return {"error": "Failed to restart TTS engine"}


# Singleton instance
bot_control_service = BotControlService()

