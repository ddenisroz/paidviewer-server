"""Extended logging helpers for API, platform, and websocket diagnostics."""

import json
import logging
import time
from functools import wraps
from typing import Any, Callable

auth_logger = logging.getLogger("auth_system")
tts_logger = logging.getLogger("tts_system")
drops_logger = logging.getLogger("drops_system")
commands_logger = logging.getLogger("commands_system")
stream_logger = logging.getLogger("stream_system")
vk_logger = logging.getLogger("vk_system")
twitch_logger = logging.getLogger("twitch_system")
api_logger = logging.getLogger("api_system")


def log_api_call(system: str):
    """Wrap an async API handler with start/success/error logging."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            logger = logging.getLogger(f"{system}_system")

            logger.info("[%s] ===== START: %s =====", system.upper(), func.__name__)
            logger.info("[%s] Args: %s", system.upper(), args)
            logger.info("[%s] Kwargs keys: %s", system.upper(), list(kwargs.keys()))

            try:
                result = await func(*args, **kwargs)
                elapsed = time.time() - start_time
                logger.info("[%s] ===== SUCCESS: %s (%.3fs) =====", system.upper(), func.__name__, elapsed)
                return result
            except Exception as exc:
                elapsed = time.time() - start_time
                logger.error("[%s] ===== ERROR: %s (%.3fs) =====", system.upper(), func.__name__, elapsed)
                logger.error("[%s] Error: %s", system.upper(), exc, exc_info=True)
                raise

        return wrapper

    return decorator


def log_function_call(logger_name: str):
    """Wrap a sync or async function with start/success/error logging."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            logger = logging.getLogger(logger_name)
            logger.info("Calling %s", func.__name__)
            try:
                result = await func(*args, **kwargs)
                logger.info("%s completed successfully", func.__name__)
                return result
            except Exception as exc:
                logger.error("%s failed: %s", func.__name__, exc)
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            logger = logging.getLogger(logger_name)
            logger.info("Calling %s", func.__name__)
            try:
                result = func(*args, **kwargs)
                logger.info("%s completed successfully", func.__name__)
                return result
            except Exception as exc:
                logger.error("%s failed: %s", func.__name__, exc)
                raise

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def log_request(endpoint: str, method: str, data: Any = None, user_id: Any = None) -> None:
    """Log an incoming API request."""

    api_logger.info("[REQUEST] [%s] %s | User: %s", method, endpoint, user_id)
    if data:
        try:
            api_logger.debug("[REQUEST DATA] %s", json.dumps(data, ensure_ascii=False, indent=2))
        except (TypeError, ValueError):
            api_logger.debug("[REQUEST DATA] %s", data)


def log_response(endpoint: str, status: int, data: Any = None, elapsed: float = None) -> None:
    """Log an API response."""

    level_tag = "[OK]" if status < 400 else "[ERROR]"
    time_suffix = f" ({elapsed:.3f}s)" if elapsed is not None else ""
    api_logger.info("%s [%s] %s%s", level_tag, status, endpoint, time_suffix)

    if data and status >= 400:
        try:
            api_logger.error("Error response: %s", json.dumps(data, ensure_ascii=False, indent=2))
        except (TypeError, ValueError):
            api_logger.error("Error response: %s", data)


def log_database_query(operation: str, table: str, filters: dict = None) -> None:
    """Log a database query or repository action."""

    db_logger = logging.getLogger("database_system")
    db_logger.debug("[DB] %s on %s | Filters: %s", operation, table, filters)


def log_websocket_event(event_type: str, user_id: Any, data: Any = None) -> None:
    """Log a websocket event."""

    ws_logger = logging.getLogger("websocket_system")
    ws_logger.info("[WS] Event: %s | User: %s | Data: %s", event_type, user_id, data)


def log_platform_api_call(platform: str, endpoint: str, status: int = None, error: str = None) -> None:
    """Log a Twitch, VK, or other platform API call."""

    platform_logger = logging.getLogger(f"{platform}_system")
    if error:
        platform_logger.error("[ERROR] API call failed: %s | Error: %s", endpoint, error)
    else:
        platform_logger.info("[OK] API call: %s | Status: %s", endpoint, status)


def get_system_metrics() -> dict[str, str]:
    """Return the canonical metric names exposed by the backend."""

    return {
        "uptime": "system_uptime_seconds",
        "requests_total": "http_requests_total",
        "errors_total": "http_errors_total",
        "active_connections": "websocket_connections_active",
        "tts_requests": "tts_requests_total",
        "memory_usage": "memory_usage_bytes",
    }
