"""Singleton registry for managing bot instances."""

import asyncio
import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from bots.twitch_bot import Bot
    from bots.vk_live_bot import VKLiveBot

logger = logging.getLogger(__name__)


class BotRegistry:
    """Singleton registry for Twitch and VK bot instances."""

    _instance: Optional["BotRegistry"] = None
    _lock = asyncio.Lock()

    def __init__(self):
        self._twitch_bot: Optional["Bot"] = None
        self._twitch_task: Optional[asyncio.Task] = None
        self._vk_bot: Optional["VKLiveBot"] = None
        self._vk_task: Optional[asyncio.Task] = None

    @classmethod
    def get_instance(cls) -> "BotRegistry":
        """Return the singleton instance."""

        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def twitch_bot(self) -> Optional["Bot"]:
        """Return the Twitch bot instance."""

        return self._twitch_bot

    @twitch_bot.setter
    def twitch_bot(self, bot: Optional["Bot"]) -> None:
        """Store the Twitch bot instance."""

        self._twitch_bot = bot

    @property
    def twitch_task(self) -> Optional[asyncio.Task]:
        """Return the Twitch bot task."""

        return self._twitch_task

    @twitch_task.setter
    def twitch_task(self, task: Optional[asyncio.Task]) -> None:
        """Store the Twitch bot task."""

        self._twitch_task = task

    def is_twitch_running(self) -> bool:
        """Check whether the Twitch bot task is running."""

        return self._twitch_bot is not None and self._twitch_task is not None and not self._twitch_task.done()

    @property
    def vk_bot(self) -> Optional["VKLiveBot"]:
        """Return the VK Live bot instance."""

        return self._vk_bot

    @vk_bot.setter
    def vk_bot(self, bot: Optional["VKLiveBot"]) -> None:
        """Store the VK Live bot instance."""

        self._vk_bot = bot

    @property
    def vk_task(self) -> Optional[asyncio.Task]:
        """Return the VK Live bot task."""

        return self._vk_task

    @vk_task.setter
    def vk_task(self, task: Optional[asyncio.Task]) -> None:
        """Store the VK Live bot task."""

        self._vk_task = task

    def is_vk_running(self) -> bool:
        """Check whether the VK Live bot is running."""

        return self._vk_bot is not None and self._vk_bot.is_running

    async def stop_twitch_bot(self) -> None:
        """Stop the Twitch bot and clear its registry state."""

        if self._twitch_task:
            self._twitch_task.cancel()
            try:
                await self._twitch_task
            except asyncio.CancelledError:
                pass
            self._twitch_task = None
        self._twitch_bot = None
        logger.info("[OK] Twitch bot stopped")

    async def stop_vk_bot(self) -> None:
        """Stop the VK Live bot and clear its registry state."""

        if self._vk_bot:
            try:
                await self._vk_bot.stop_bot()
            except Exception as exc:
                logger.error("[ERROR] Error stopping VK bot: %s", exc)
        if self._vk_task:
            self._vk_task.cancel()
            try:
                await self._vk_task
            except asyncio.CancelledError:
                pass
            self._vk_task = None
        self._vk_bot = None
        logger.info("[OK] VK Live bot stopped")

    async def stop_all(self) -> None:
        """Stop all registered bots."""

        await self.stop_twitch_bot()
        await self.stop_vk_bot()


def get_bot_registry() -> BotRegistry:
    """Return the singleton bot registry instance."""

    return BotRegistry.get_instance()


# Backward compatibility for older imports.
def get_bot_instance():
    """Return the Twitch bot instance for compatibility wrappers."""

    return get_bot_registry().twitch_bot


def get_vk_bot_instance():
    """Return the VK Live bot instance for compatibility wrappers."""

    return get_bot_registry().vk_bot
