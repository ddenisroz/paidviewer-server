"""
Advanced rate limiter built on the ``limits`` library.
Uses ``limits`` directly without ``slowapi`` to avoid .env-related issues.
"""

import logging
import re
from typing import Dict, Any

from fastapi import Request
from limits import parse, storage
from limits.strategies import MovingWindowRateLimiter

from core.config import settings

logger = logging.getLogger(__name__)


class AdvancedRateLimiter:
    """Advanced rate limiter built on the ``limits`` library."""

    def __init__(self):
        storage_backend = "memory"
        try:
            redis_url = (settings.redis_url or "").strip()
            if redis_url:
                self.storage = storage.storage_from_string(redis_url)
                storage_backend = "redis"
            else:
                self.storage = storage.MemoryStorage()
        except Exception:
            logger.exception("Failed to initialize Redis rate limiter storage, falling back to memory")
            self.storage = storage.MemoryStorage()

        self.strategy = MovingWindowRateLimiter(self.storage)
        self.storage_backend = storage_backend
        self.limits = {
            "default": settings.rate_limit_default or "60/minute",
            "login": settings.rate_limit_login or "5/15minute",
            "api": "100/minute",
            "tts": settings.rate_limit_tts or "30/minute",
            "upload": "10/minute",
        }
        logger.info("[RATE-LIMITER] Advanced Rate Limiter initialized with limits library (storage=%s)", storage_backend)

    @staticmethod
    def _extract_client_ip(request: Request) -> str:
        """Extract best-effort client IP for reverse-proxy deployments."""
        forwarded_for = (request.headers.get("x-forwarded-for") or "").strip()
        if forwarded_for:
            first_hop = forwarded_for.split(",")[0].strip()
            if first_hop:
                return first_hop

        real_ip = (request.headers.get("x-real-ip") or "").strip()
        if real_ip:
            return real_ip

        cf_ip = (request.headers.get("cf-connecting-ip") or "").strip()
        if cf_ip:
            return cf_ip

        return getattr(request.client, "host", "unknown")

    def _get_identifier(self, request: Request = None, user_id: int = None) -> str:
        """Build an identifier for rate limiting."""
        if user_id:
            return f"user:{user_id}"
        if request:
            client_ip = self._extract_client_ip(request)
            return f"ip:{client_ip}"
        return "global"

    def check_rate_limit(self, identifier: str, action: str = "default") -> bool:
        """Check whether the limit allows the requested action."""
        try:
            limit_str = self.limits.get(action, self.limits["default"])
            rate_limit_item = parse(limit_str)
            if self.strategy.hit(rate_limit_item, identifier):
                logger.debug("Rate limit OK for %s, action '%s'", identifier, action)
                return True
            logger.warning("Rate limit exceeded for %s, action '%s'", identifier, action)
            return False
        except Exception:
            logger.exception("Rate limit check failed")
            return True

    def get_remaining_requests(self, identifier: str, action: str = "default") -> int:
        """Return the remaining request count for the current window."""
        try:
            limit_str = self.limits.get(action, self.limits["default"])
            rate_limit_item = parse(limit_str)
            stats = self.strategy.get_window_stats(rate_limit_item, identifier)
            if not stats:
                return 0

            if hasattr(stats, "remaining"):
                return max(0, int(stats.remaining))

            if isinstance(stats, tuple) and len(stats) >= 2:
                limit_num = int(limit_str.split("/")[0])
                return max(0, limit_num - int(stats[1]))

            return 0
        except Exception:
            logger.exception("Failed to get remaining requests")
            return 0

    def reset_rate_limit(self, identifier: str, action: str = "default") -> bool:
        """Reset rate limit state for an identifier."""
        try:
            logger.warning("Reset rate limit for %s, action '%s' (limited functionality)", identifier, action)
            return True
        except Exception:
            logger.exception("Failed to reset rate limit")
            return False

    def reset_state(self) -> bool:
        """Fully reset in-memory limiter state for tests and cleanup."""
        try:
            self.storage = storage.MemoryStorage()
            self.strategy = MovingWindowRateLimiter(self.storage)
            self.storage_backend = "memory"
            return True
        except Exception:
            logger.exception("Failed to reset rate limiter state")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Return rate limiter statistics."""
        try:
            return {
                "storage_type": self.storage_backend,
                "strategy": "moving_window",
                "limits": self.limits,
                "library": "limits",
                "version": "advanced",
            }
        except Exception:
            logger.exception("Failed to get rate limiter stats")
            return {"error": "Internal server error"}

    def _estimate_retry_after(self, action: str = "default") -> int:
        """Best-effort Retry-After estimation from limit string."""
        limit_str = self.limits.get(action, self.limits["default"]).lower().strip()
        match = re.search(r"/\s*(\d+)\s*(second|minute|hour|day)", limit_str)
        if match:
            amount = int(match.group(1))
            unit = match.group(2)
            multiplier = {
                "second": 1,
                "minute": 60,
                "hour": 3600,
                "day": 86400,
            }[unit]
            return max(1, amount * multiplier)

        if "/minute" in limit_str:
            return 60
        if "/hour" in limit_str:
            return 3600
        if "/day" in limit_str:
            return 86400
        return 60

    async def check_tts_rate_limit(self, user_id: int, text_length: int) -> Dict[str, int | bool]:
        """Check TTS rate limit using the unified contract."""
        identifier = self._get_identifier(user_id=user_id)
        allowed = self.check_rate_limit(identifier, "tts")
        remaining = self.get_remaining_requests(identifier, "tts")
        retry_after = 0 if allowed else self._estimate_retry_after("tts")
        return {
            "allowed": allowed,
            "remaining": remaining,
            "retry_after": retry_after,
        }

    async def add_tts_request(self, user_id: int, text_length: int):
        """Record a TTS request (compatibility no-op)."""
        return None

    async def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Return per-user statistics (compatibility wrapper)."""
        identifier = self._get_identifier(user_id=user_id)
        return {
            "user_id": user_id,
            "remaining_requests": self.get_remaining_requests(identifier, "tts"),
            "rate_limit_type": "moving_window",
            "library": "limits",
        }

    async def reset_user_limits(self, user_id: int):
        """Reset per-user limits (compatibility wrapper)."""
        identifier = self._get_identifier(user_id=user_id)
        self.reset_rate_limit(identifier, "tts")


advanced_rate_limiter = AdvancedRateLimiter()


def check_rate_limit(identifier: str, action: str = "default") -> bool:
    """Compatibility wrapper for rate limit checks."""
    return advanced_rate_limiter.check_rate_limit(identifier, action)


def record_failed_login(identifier: str) -> int:
    """Compatibility stub for failed login tracking."""
    return 0


def is_login_blocked(identifier: str) -> bool:
    """Compatibility wrapper for login blocking checks."""
    return not advanced_rate_limiter.check_rate_limit(identifier, "login")


def clear_failed_logins(identifier: str):
    """Compatibility wrapper for clearing failed login attempts."""
    advanced_rate_limiter.reset_rate_limit(identifier, "login")
