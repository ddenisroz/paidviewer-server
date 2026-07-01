"""Redis-backed command cooldown storage with safe memory fallback."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

from redis import Redis

from core.config import settings
from core.database import BotCommand
from core.datetime_utils import utcnow_naive

logger = logging.getLogger("bot_service")


class CommandCooldownStore:
    """Manage command cooldown state across processes when Redis is available."""

    def __init__(
        self,
        redis_client: Optional[Redis] = None,
        redis_url: Optional[str] = None,
    ) -> None:
        self._memory_cooldowns: Dict[str, datetime] = {}
        self._redis_client = redis_client
        self._backend = "memory"

        if redis_client is not None:
            self._backend = "redis"
            return

        redis_target = (redis_url or settings.redis_url or "").strip()
        if not redis_target:
            return

        try:
            self._redis_client = Redis.from_url(
                redis_target,
                decode_responses=True,
                socket_connect_timeout=0.2,
                socket_timeout=0.2,
                retry_on_timeout=False,
            )
            self._backend = "redis"
        except Exception:
            logger.exception("Failed to initialize Redis cooldown store, using memory fallback")
            self._redis_client = None
            self._backend = "memory"

    @property
    def backend(self) -> str:
        return self._backend

    @staticmethod
    def _normalize_part(value: object, *, default: str) -> str:
        raw = str(value).strip().lower() if value is not None else ""
        if not raw:
            return default
        return raw.replace(" ", "_")

    def _build_key(self, command: BotCommand, user_id: str) -> str:
        platform = self._normalize_part(command.platforms, default="any")
        channel = self._normalize_part(command.channel_name, default="default")
        owner = self._normalize_part(command.user_id, default="global")
        viewer = self._normalize_part(user_id, default="anonymous")
        command_id = self._normalize_part(command.id, default="unknown")

        return (
            "command-cooldown:v1:"
            f"platform:{platform}:channel:{channel}:owner:{owner}:"
            f"command:{command_id}:viewer:{viewer}"
        )

    def _use_memory_fallback(self, action: str) -> None:
        if self._backend == "redis":
            logger.exception("Redis cooldown %s failed, switching to memory fallback", action)
        self._backend = "memory"
        self._redis_client = None

    def _cleanup_expired(self) -> None:
        now = utcnow_naive()
        expired_keys = [key for key, expires_at in self._memory_cooldowns.items() if now >= expires_at]
        for key in expired_keys:
            self._memory_cooldowns.pop(key, None)

    def is_available(self, command: BotCommand, user_id: str) -> bool:
        if command.cooldown_seconds <= 0:
            return True

        key = self._build_key(command, user_id)

        if self._redis_client is not None:
            try:
                return not bool(self._redis_client.exists(key))
            except Exception:
                self._use_memory_fallback("check")

        self._cleanup_expired()
        expires_at = self._memory_cooldowns.get(key)
        return expires_at is None or utcnow_naive() >= expires_at

    def mark_used(self, command: BotCommand, user_id: str) -> None:
        if command.cooldown_seconds <= 0:
            return

        key = self._build_key(command, user_id)

        if self._redis_client is not None:
            try:
                self._redis_client.setex(key, int(command.cooldown_seconds), "1")
                return
            except Exception:
                self._use_memory_fallback("update")

        self._cleanup_expired()
        self._memory_cooldowns[key] = utcnow_naive() + timedelta(seconds=command.cooldown_seconds)


_default_cooldown_store: Optional[CommandCooldownStore] = None


def get_command_cooldown_store() -> CommandCooldownStore:
    global _default_cooldown_store

    if _default_cooldown_store is None:
        _default_cooldown_store = CommandCooldownStore()

    return _default_cooldown_store
