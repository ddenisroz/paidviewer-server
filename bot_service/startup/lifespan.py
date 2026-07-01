"""Application startup and shutdown lifecycle hooks."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from core.background_tasks import background_tasks
from core.config import settings
from core.connection_manager import get_connection_manager
from core.database import get_db, init_db
from services.memory_websocket_manager import get_memory_websocket_manager
from services.tts.memory_tts_queue import get_memory_tts_queue

from .bot_initializer import initialize_all_bots
from .bot_registry import get_bot_registry

logger = logging.getLogger(__name__)


async def _startup_database() -> None:
    """Initialize the database layer."""

    create_schema = bool(settings.is_development)
    if create_schema:
        logger.info("Development mode detected: ensuring database schema before seeding")

    init_db(create_schema=create_schema, strict=True)
    logger.info("Database initialized")


async def _startup_commands() -> None:
    """Idempotently refresh the full global command catalog on every startup."""

    try:
        logger.info("[STARTUP] Seeding or refreshing global bot commands")
        from init_global_commands import init_global_commands

        init_global_commands()
    except Exception as exc:
        logger.error("Failed to seed global commands: %s", exc)


async def _startup_services() -> None:
    """Start core runtime services in parallel."""

    from services.tts.tts_worker import tts_worker
    from services.worker_control.reconciler import worker_control_reconciler

    try:
        await asyncio.gather(
            get_memory_tts_queue().start(),
            get_memory_websocket_manager().start(),
            tts_worker.start(),
            worker_control_reconciler.start(),
        )
        logger.info("All services started (TTS queue, WebSocket manager, TTS worker, worker reconciler)")
    except Exception as exc:
        logger.error("Failed to start services: %s", exc)
        raise


async def _startup_connection_manager() -> None:
    """Restore active channel sessions into the connection manager."""

    connection_manager = get_connection_manager()
    db = next(get_db())

    try:
        await connection_manager.restore_active_sessions_from_db(db)
        active_channels = connection_manager.get_active_channels()
        logger.info("Restored %s active channels", len(active_channels))
        logger.info("[OK] TTS will be enabled when users connect via WebSocket")
    finally:
        db.close()


async def _startup_background_tasks() -> None:
    """Start background task services in parallel."""

    from services.bot_token_validator import bot_token_validator
    from services.vk_token_refresh_service import vk_token_refresh_service

    await asyncio.gather(
        background_tasks.start_all_tasks(),
        bot_token_validator.start_monitoring(check_interval=3600),
        vk_token_refresh_service.start(),
    )
    logger.info("All background tasks started (tasks, token monitoring, VK refresh)")


async def _shutdown_bots() -> None:
    """Stop all running bot instances."""

    registry = get_bot_registry()
    connection_manager = get_connection_manager()

    active_vk_bots = getattr(connection_manager, "active_vk_bots", {})
    logger.info("[CLEANUP] Cleaning up %s active VK bots...", len(active_vk_bots))

    for channel_name, bot_data in list(active_vk_bots.items()):
        try:
            vk_bot = bot_data.get("bot")
            if vk_bot:
                await vk_bot.disconnect()
                logger.info("[OK] VK bot disconnected from %s", channel_name)
        except Exception as exc:
            logger.error("[ERROR] Error disconnecting VK bot from %s: %s", channel_name, exc)

    await registry.stop_all()


async def _shutdown_services() -> None:
    """Stop core runtime services."""

    try:
        await get_memory_tts_queue().stop()
    except Exception as exc:
        logger.error("Error stopping Memory TTS Queue: %s", exc)

    try:
        await get_memory_websocket_manager().stop()
    except Exception as exc:
        logger.error("Error stopping Memory WebSocket Manager: %s", exc)

    try:
        from services.tts.tts_worker import tts_worker

        await tts_worker.stop()
    except Exception as exc:
        logger.error("Error stopping TTS Worker: %s", exc)

    try:
        from services.worker_control.reconciler import worker_control_reconciler

        await worker_control_reconciler.stop()
    except Exception as exc:
        logger.error("Error stopping worker control reconciler: %s", exc)


async def _shutdown_background_tasks() -> None:
    """Stop background task services."""

    from services.bot_token_validator import bot_token_validator
    from services.vk_token_refresh_service import vk_token_refresh_service

    await bot_token_validator.stop_monitoring()
    logger.info("Bot token monitoring stopped")

    await vk_token_refresh_service.stop()
    logger.info("VK token refresh service stopped")

    await background_tasks.stop_all_tasks()
    logger.info("Background tasks stopped")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI lifespan manager for startup and shutdown logic."""

    if settings.testing:
        logger.info("Testing mode enabled: skipping heavy startup/shutdown services")
        yield
        return

    logger.info("Bot service starting on port 8000")

    try:
        await _startup_database()
        await _startup_commands()
        await _startup_services()
        await _startup_connection_manager()
        await _startup_background_tasks()
        await initialize_all_bots()
        logger.info("=== BOT SERVICE STARTED ===")
    except Exception as exc:
        logger.error("Error during startup: %s", exc)
        raise

    yield

    logger.info("Bot service shutting down")

    try:
        await _shutdown_bots()
        await _shutdown_background_tasks()
        await _shutdown_services()
        logger.info("Connections cleaned up")
        logger.info("=== BOT SERVICE STOPPED ===")
    except Exception as exc:
        logger.error("Error during shutdown: %s", exc)
