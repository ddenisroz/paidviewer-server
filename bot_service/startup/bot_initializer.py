# bot_service/startup/bot_initializer.py
"""
Bot startup helpers.

Production model:
- Dedicated bot OAuth tokens are stored in DB (`bot_tokens`).
- No legacy env token fallback is used at runtime.
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

from bots.twitch_bot import Bot
from bots.vk_live_bot import VKLiveBot
from core.config import settings
from core.connection_manager import get_connection_manager
from core.database import get_db
from services.bot_token_validator import bot_token_validator
from services.twitch_bot_oauth_service import twitch_bot_oauth_service
from services.vk_bot_oauth_service import vk_bot_oauth_service

from .bot_registry import get_bot_registry

logger = logging.getLogger(__name__)


async def initialize_twitch_bot(channels: Optional[List[str]] = None) -> bool:
    """
    Start Twitch bot using OAuth token from DB only.

    Args:
        channels: Optional channel list to join after bot startup.
    """
    registry = get_bot_registry()
    if registry.is_twitch_running():
        logger.info("[INFO] Twitch bot already running")
        return True

    bot_token_data = None
    db = next(get_db())
    try:
        bot_token_data = await twitch_bot_oauth_service.get_bot_token(db)
        if not bot_token_data or not bot_token_data.get("access_token"):
            logger.warning("[WARN] Twitch bot OAuth token not configured.")
            logger.warning("[FIX] Configure a dedicated Twitch bot account:")
            logger.warning("[FIX] Go to /auth/twitch/bot/login")
            logger.warning("[FIX] Alternative: generate one-time link at /api/admin/bot/twitch/login-link")
            return False

        # Proactive refresh for soon-expiring tokens.
        await twitch_bot_oauth_service.refresh_if_needed(db)
        bot_token_data = await twitch_bot_oauth_service.get_bot_token(db)
    finally:
        db.close()

    if not bot_token_data or not bot_token_data.get("access_token"):
        logger.error("[ERROR] Twitch bot token exists in DB but access_token is missing")
        logger.error("[FIX] Re-authorize bot via /auth/twitch/bot/login")
        logger.error("[FIX] Alternative: /api/admin/bot/twitch/login-link")
        return False

    validation_result = await bot_token_validator.validate_twitch_bot_token()
    if not validation_result.get("valid"):
        if validation_result.get("transient"):
            logger.warning("[TWITCH] Bot token validation is temporarily unavailable; bot startup will retry later")
            logger.warning(f"[TWITCH] Reason: {validation_result.get('error', 'Unknown')}")
            return False
        logger.error("[ERROR] [TWITCH] Cannot start bot with invalid token!")
        logger.error(f"[ERROR] Reason: {validation_result.get('error', 'Unknown')}")
        logger.error("[FIX] Re-authorize bot via /auth/twitch/bot/login")
        logger.error("[FIX] Alternative: /api/admin/bot/twitch/login-link")
        return False

    token = bot_token_data["access_token"]
    bot_token = token if token.startswith("oauth:") else f"oauth:{token}"

    try:
        connection_manager = get_connection_manager()
        target_channels = list(dict.fromkeys(channels or []))

        logger.info("=" * 80)
        logger.info("[TWITCH] Creating Twitch bot instance...")
        logger.info("[TWITCH] Token validated: OK")
        logger.info(f"[TWITCH] Bot user: {validation_result.get('login', 'unknown')}")
        logger.info(f"[TWITCH] Channels to connect: {target_channels}")
        logger.info("=" * 80)

        bot = Bot(bot_token, target_channels, connection_manager)
        task = asyncio.create_task(bot.start())

        registry.twitch_bot = bot
        registry.twitch_task = task

        logger.info("[TWITCH] Task created, waiting for ready signal...")
        try:
            await asyncio.wait_for(bot.ready_event.wait(), timeout=12)
        except asyncio.TimeoutError:
            logger.error("[ERROR] [TWITCH] Bot did not become ready within 12 seconds")
            await registry.stop_twitch_bot()
            return False

        if task.done():
            logger.error("[ERROR] [TWITCH] Bot task completed unexpectedly!")
            if task.exception():
                logger.error(f"[ERROR] [TWITCH] Task exception: {task.exception()}")
            registry.twitch_bot = None
            registry.twitch_task = None
            return False

        logger.info(f"[OK] [TWITCH] Bot connected as: {bot.nick}")
        logger.info("[OK] Twitch bot started")
        return True
    except Exception as e:
        logger.error(f"[ERROR] Twitch bot initialization failed: {e}", exc_info=True)
        return False


async def initialize_vk_bot(channels: Optional[List[str]] = None) -> bool:
    """
    Start VK bot using OAuth token from DB only.

    Args:
        channels: Optional VK channel slug list to connect after startup.
    """
    registry = get_bot_registry()
    if registry.is_vk_running():
        logger.info("[INFO] VK Live bot already running")
        return True

    bot_token_data = None
    db = next(get_db())
    try:
        bot_token_data = await vk_bot_oauth_service.get_bot_token(db)
        if not bot_token_data or not bot_token_data.get("access_token"):
            logger.warning("[WARN] VK bot OAuth token not configured.")
            logger.warning("[FIX] Configure a dedicated VK bot account:")
            logger.warning("[FIX] Go to /auth/vk/bot/login")
            logger.warning("[FIX] Alternative: generate one-time link at /api/admin/bot/vk/login-link")
            return False

        # Proactive refresh for soon-expiring tokens.
        await vk_bot_oauth_service.refresh_if_needed(db)
        bot_token_data = await vk_bot_oauth_service.get_bot_token(db)
    finally:
        db.close()

    if not bot_token_data or not bot_token_data.get("access_token"):
        logger.error("[ERROR] VK bot token exists in DB but access_token is missing")
        logger.error("[FIX] Re-authorize bot via /auth/vk/bot/login")
        logger.error("[FIX] Alternative: /api/admin/bot/vk/login-link")
        return False

    validation_result = await bot_token_validator.validate_vk_bot_token()
    if not validation_result.get("valid"):
        logger.error("[ERROR] [VK] Cannot start bot with invalid token!")
        logger.error(f"[ERROR] Reason: {validation_result.get('error', 'Unknown')}")
        logger.error("[FIX] Re-authorize bot via /auth/vk/bot/login")
        logger.error("[FIX] Alternative: /api/admin/bot/vk/login-link")
        return False

    access_token = bot_token_data["access_token"]

    try:
        connection_manager = get_connection_manager()
        target_channels = list(dict.fromkeys(channels or []))

        logger.info("=" * 80)
        logger.info("[VK] Creating VK bot instance...")
        logger.info("[VK] Token validated: OK")
        logger.info(
            "[VK] Bot user: %s",
            validation_result.get("username") or validation_result.get("login") or "unknown",
        )
        logger.info(f"[VK] Channels to connect: {target_channels}")
        logger.info("=" * 80)

        bot = VKLiveBot(access_token, connection_manager)
        # VK bot's start_bot() is a simple flag setter that returns immediately
        # (unlike Twitch which runs a persistent event loop).
        # So we await it directly instead of creating a task.
        await bot.start_bot()

        registry.vk_bot = bot
        registry.vk_task = None  # VK bot uses per-channel WebSocket tasks, not a single main task

        for channel_name in target_channels:
            logger.info(f"[VK] Connecting bot to channel: {channel_name}")
            success = await bot.connect_to_channel(channel_name)
            if success:
                logger.info(f"[OK] VK bot connected to {channel_name}")
            else:
                logger.error(f"[ERROR] Failed to connect VK bot to {channel_name}")

        logger.info("[OK] VK bot started")
        return True
    except Exception as e:
        logger.error(f"[ERROR] VK bot initialization failed: {e}", exc_info=True)
        return False


async def initialize_all_bots() -> None:
    """Initialize all bots during application startup."""
    if settings.testing:
        logger.info("[TEST] Testing mode: skipping bot initialization")
        return

    connection_manager = get_connection_manager()
    db = next(get_db())
    try:
        twitch_channels = await connection_manager.get_twitch_channels_for_bot(db)
        vk_channels = await connection_manager.get_vk_channels_for_bot(db)

        logger.info(f"[STARTUP] Twitch channels: {twitch_channels}")
        logger.info(f"[STARTUP] VK channels: {vk_channels}")

        if twitch_channels:
            await initialize_twitch_bot(twitch_channels)
        else:
            logger.info("[STARTUP] No active Twitch channels found; skipping Twitch bot initialization")

        if vk_channels:
            await initialize_vk_bot(vk_channels)
        else:
            logger.info("[STARTUP] No active VK channels found; skipping VK bot initialization")
    except Exception as e:
        logger.error(f"[ERROR] Bot initialization failed: {e}")
    finally:
        db.close()
