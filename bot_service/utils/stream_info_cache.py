# utils/stream_info_cache.py
"""In-memory cache for stream info (per user/platform)."""
from __future__ import annotations

import time
from typing import Optional

STREAM_INFO_CACHE_TTL = 60  # seconds
_stream_info_cache: dict[tuple[int, str], tuple[dict, float]] = {}


def get_cached_stream_info(user_id: int, platform: str) -> Optional[dict]:
    """Return cached stream info if not expired."""
    key = (user_id, platform)
    if key in _stream_info_cache:
        data, timestamp = _stream_info_cache[key]
        if time.time() - timestamp < STREAM_INFO_CACHE_TTL:
            return data
        del _stream_info_cache[key]
    return None


def set_cached_stream_info(user_id: int, platform: str, data: dict) -> None:
    """Store stream info in cache with a fresh timestamp."""
    _stream_info_cache[(user_id, platform)] = (data, time.time())


def invalidate_stream_info_cache(user_id: int, platform: Optional[str] = None) -> None:
    """Invalidate cache for a user (optionally for a specific platform)."""
    if platform:
        _stream_info_cache.pop((user_id, platform), None)
        return

    keys = [key for key in _stream_info_cache if key[0] == user_id]
    for key in keys:
        del _stream_info_cache[key]
