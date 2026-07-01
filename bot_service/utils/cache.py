"""Small in-memory cache helpers for frequent runtime lookups."""

import logging
import time
from functools import wraps
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# Simple in-memory cache. Redis is preferred for larger production setups.
_cache: dict[str, tuple[Any, float]] = {}
CACHE_TTL = 300

# Dedicated TTL values for common data classes.
TTL_WHITELIST = 300
TTL_USER_SETTINGS = 180
TTL_USER_DATA = 120


def get_cached(key: str, func: Callable, *args, ttl: Optional[float] = None, **kwargs) -> Any:
    """Return a cached value or compute and cache it."""

    ttl = ttl or CACHE_TTL

    if key in _cache:
        value, timestamp = _cache[key]
        if time.time() - timestamp < ttl:
            logger.debug("Cache HIT: %s", key)
            return value

        del _cache[key]
        logger.debug("Cache EXPIRED: %s", key)

    logger.debug("Cache MISS: %s", key)
    value = func(*args, **kwargs)
    _cache[key] = (value, time.time())
    return value


def invalidate_cache(pattern: Optional[str] = None):
    """Invalidate the whole cache or only keys that match a substring."""

    if pattern is None:
        _cache.clear()
        logger.info("Cache cleared")
        return

    keys_to_delete = [key for key in _cache if pattern in key]
    for key in keys_to_delete:
        del _cache[key]
    logger.info("Cache invalidated for pattern: %s, deleted %s keys", pattern, len(keys_to_delete))


def cache_decorator(ttl: Optional[float] = None, key_prefix: str = ""):
    """Decorator for caching a function result in the process cache."""

    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = f"{key_prefix}:{func.__name__}:{str(args)}:{str(sorted(kwargs.items()))}"
            return get_cached(cache_key, func, *args, ttl=ttl, **kwargs)

        return wrapper

    return decorator


def get_cache_stats() -> dict:
    """Return basic process-cache statistics."""

    now = time.time()
    active_entries = 0
    expired_entries = 0

    for _, (_, timestamp) in _cache.items():
        if now - timestamp < CACHE_TTL:
            active_entries += 1
        else:
            expired_entries += 1

    return {
        "total_entries": len(_cache),
        "active_entries": active_entries,
        "expired_entries": expired_entries,
        "cache_size_mb": sum(len(str(value[0])) for value in _cache.values()) / 1024 / 1024,
    }
