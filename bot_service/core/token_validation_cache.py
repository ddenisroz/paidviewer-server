# bot_service/core/token_validation_cache.py
"""In-memory cache for token validation results."""
import time
import logging
from typing import Dict, Tuple, Optional
from threading import Lock

logger = logging.getLogger(__name__)

class TokenValidationCache:
    """
    Simple thread-safe cache for token validation results.

    Uses ``(user_id, platform)`` as the key and stores
    ``(is_valid, timestamp)`` as the value.
    """

    # Cache TTL in seconds (5 minutes).
    DEFAULT_TTL = 300

    def __init__(self, ttl: int = DEFAULT_TTL):
        self._cache: Dict[Tuple[int, str], Tuple[bool, float]] = {}
        self._lock = Lock()
        self.ttl = ttl
        logger.info(f"[OK] TokenValidationCache initialized with TTL={ttl}s")

    def get(self, user_id: int, platform: str) -> Optional[bool]:
        """
        Return a cached validation result.

        Returns:
            The cached validation result or ``None`` if it is missing or expired.
        """
        key = (user_id, platform)

        with self._lock:
            if key not in self._cache:
                return None

            is_valid, cached_at = self._cache[key]
            age = time.time() - cached_at

            # Check TTL.
            if age > self.ttl:
                logger.debug(f" [CACHE] Expired for user {user_id}, platform {platform} (age: {age:.1f}s)")
                del self._cache[key]
                return None

            logger.debug(f"[OK] [CACHE HIT] user {user_id}, platform {platform}, valid={is_valid}, age={age:.1f}s")
            return is_valid

    def set(self, user_id: int, platform: str, is_valid: bool):
        """
        Store a validation result in the cache.
        """
        key = (user_id, platform)

        with self._lock:
            self._cache[key] = (is_valid, time.time())
            logger.debug(f"[DB] [CACHE SET] user {user_id}, platform {platform}, valid={is_valid}")

    def invalidate(self, user_id: int, platform: str = None):
        """
        Invalidate cached results for a user.

        Args:
            user_id: User ID
            platform: Specific platform or ``None`` for all platforms
        """
        with self._lock:
            if platform:
                # Invalidate one platform entry.
                key = (user_id, platform)
                if key in self._cache:
                    del self._cache[key]
                    logger.debug(f"[DELETE] [CACHE INVALIDATE] user {user_id}, platform {platform}")
            else:
                # Invalidate all cached platforms for the user.
                keys_to_delete = [k for k in self._cache.keys() if k[0] == user_id]
                for key in keys_to_delete:
                    del self._cache[key]
                logger.debug(f"[DELETE] [CACHE INVALIDATE] user {user_id}, all platforms ({len(keys_to_delete)} entries)")

    def clear(self):
        """Clear the entire cache."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"[DELETE] [CACHE CLEAR] Cleared {count} entries")

    def cleanup_expired(self):
        """
        Remove expired cache entries.

        This method is safe to call periodically from a background task.
        """
        now = time.time()

        with self._lock:
            expired_keys = [
                key for key, (_, cached_at) in self._cache.items()
                if now - cached_at > self.ttl
            ]

            for key in expired_keys:
                del self._cache[key]

            if expired_keys:
                logger.info(f"[CLEANUP] [CACHE CLEANUP] Removed {len(expired_keys)} expired entries")

    def get_stats(self) -> Dict[str, int]:
        """Return cache statistics."""
        with self._lock:
            return {
                "total_entries": len(self._cache),
                "ttl_seconds": self.ttl
            }


# Singleton instance
token_validation_cache = TokenValidationCache()

