# bot_service/core/structured_logging.py
"""
Structured Logging Configuration

Provides JSON-formatted logs with context for better debugging and monitoring.

Features:
- JSON output for production
- Human-readable output for development
- Automatic context injection (user_id, request_id, etc.)
- Integration with Sentry
- Log rotation
"""
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict

import structlog
from structlog.types import EventDict, Processor

from core.config import settings

module_logger = logging.getLogger(__name__)

_SENSITIVE_TEXT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)(authorization\\s*[:=]\\s*)(bearer\\s+)?[^\\s,;]+"), r"\\1[FILTERED]"),
    (re.compile(r"(?i)(access_token\\s*[:=]\\s*)[^\\s,;]+"), r"\\1[FILTERED]"),
    (re.compile(r"(?i)(refresh_token\\s*[:=]\\s*)[^\\s,;]+"), r"\\1[FILTERED]"),
    (re.compile(r"(?i)(client_secret\\s*[:=]\\s*)[^\\s,;]+"), r"\\1[FILTERED]"),
    (re.compile(r"(?i)(api[_-]?key\\s*[:=]\\s*)[^\\s,;]+"), r"\\1[FILTERED]"),
    (re.compile(r"(?i)(password\\s*[:=]\\s*)[^\\s,;]+"), r"\\1[FILTERED]"),
    (re.compile(r"(?i)(code\\s*[:=]\\s*)[^\\s,;]+"), r"\\1[FILTERED]"),
    (re.compile(r"(?i)(state\\s*[:=]\\s*)[^\\s,;]+"), r"\\1[FILTERED]"),
    (re.compile(r"(?i)(session_id\\s*[:=]\\s*)[^\\s,;]+"), r"\\1[FILTERED]"),
]


def _redact_text(value: str) -> str:
    redacted = value
    for pattern, replacement in _SENSITIVE_TEXT_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def _redact_object(value: Any) -> Any:
    if isinstance(value, dict):
        result: Dict[Any, Any] = {}
        for key, item in value.items():
            key_str = str(key).lower()
            if any(
                s in key_str
                for s in (
                    "authorization",
                    "token",
                    "secret",
                    "password",
                    "api_key",
                    "code",
                    "state",
                    "session_id",
                )
            ):
                result[key] = "[FILTERED]"
            else:
                result[key] = _redact_object(item)
        return result
    if isinstance(value, (list, tuple)):
        redacted_seq = [_redact_object(item) for item in value]
        return type(value)(redacted_seq)
    if isinstance(value, str):
        return _redact_text(value)
    return value


class SensitiveDataFilter(logging.Filter):
    """Log filter that redacts sensitive values in stdlib logging records."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        try:
            if isinstance(record.msg, str):
                record.msg = _redact_text(record.msg)
            if record.args:
                record.args = _redact_object(record.args)
        except Exception:
            # Never block logging because of redaction errors.
            return True
        return True


class RepeatedNoiseFilter(logging.Filter):
    """Throttle known duplicate third-party log records that can flood local logs."""

    def __init__(self, throttle_seconds: int | None = None) -> None:
        super().__init__()
        if throttle_seconds is None:
            raw_value = os.getenv("NOISY_LOG_THROTTLE_SECONDS", "300")
            try:
                throttle_seconds = int(raw_value)
            except ValueError:
                throttle_seconds = 300

        self.throttle_seconds = max(0, throttle_seconds)
        self._last_seen: dict[tuple[str, str], float] = {}

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        if self.throttle_seconds <= 0:
            return True

        try:
            message = record.getMessage()
        except Exception:
            return True

        if record.name == "twitchio.websocket" and message == "Websocket connection was closed: None":
            key = (record.name, message)
            now = time.monotonic()
            last_seen = self._last_seen.get(key)
            if last_seen is not None and now - last_seen < self.throttle_seconds:
                return False
            self._last_seen[key] = now

        return True


def add_app_context(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """
    Add application context to all log entries.
    
    This adds:
    - environment (development/production)
    - service name
    - version
    """
    event_dict["environment"] = settings.environment
    event_dict["service"] = "bot_service"
    event_dict["version"] = "0.03"
    return event_dict


def add_severity_level(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """
    Add severity level for better filtering.
    
    Maps structlog levels to standard severity levels.
    """
    level_mapping = {
        "debug": "DEBUG",
        "info": "INFO",
        "warning": "WARNING",
        "error": "ERROR",
        "critical": "CRITICAL",
    }
    
    if "level" in event_dict:
        event_dict["severity"] = level_mapping.get(event_dict["level"], "INFO")
    
    return event_dict


def censor_sensitive_data(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """
    Censor sensitive data from logs.
    
    Replaces sensitive fields with [FILTERED].
    """
    sensitive_fields = [
        "password", "token", "secret", "api_key", 
        "access_token", "refresh_token", "authorization", "session_id"
    ]
    
    def censor_dict(d: Dict) -> Dict:
        """Recursively censor dictionary"""
        result = {}
        for key, value in d.items():
            if any(sensitive in key.lower() for sensitive in sensitive_fields):
                result[key] = "[FILTERED]"
            elif isinstance(value, dict):
                result[key] = censor_dict(value)
            else:
                result[key] = value
        return result
    
    return censor_dict(event_dict)


_SETUP_DONE = False


def _resolve_log_level(level_name: Any, default_level: int = logging.INFO) -> int:
    """Resolve log level name (e.g. INFO) to logging constant."""
    raw_name = str(level_name or "").strip().upper()
    if not raw_name:
        return default_level

    resolved = logging.getLevelName(raw_name)
    if isinstance(resolved, int):
        return resolved

    module_logger.warning(
        "Invalid log level '%s', falling back to %s",
        level_name,
        logging.getLevelName(default_level),
    )
    return default_level


def _configure_console_streams_for_utf8() -> None:
    """
    Ensure stdout/stderr are UTF-8 so Cyrillic logs are readable on Windows terminals.

    Safe no-op for environments that do not support stream reconfiguration.
    """
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue

        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue

        try:
            reconfigure(encoding="utf-8", errors="replace", newline="\n", line_buffering=True)
        except TypeError:
            # Fallback for Python builds without full reconfigure signature support.
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                continue
        except Exception:
            continue


def _should_use_plain_file_handler() -> bool:
    """
    Windows + development mode usually means uvicorn reload with multiple processes.

    RotatingFileHandler is not safe in that setup because rollover renames the active
    log file and frequently fails with WinError 32 when another process still holds it.
    """
    return os.name == "nt" and settings.is_development


def _create_file_log_handler(log_file: Path, file_log_level: int) -> logging.Handler | None:
    """Create the file log handler with a Windows-safe development fallback."""
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if _should_use_plain_file_handler():
        handler = logging.FileHandler(log_file, encoding="utf-8")
        module_logger.info(
            "Using plain FileHandler for '%s' on Windows development runtime to avoid reload rotation conflicts.",
            log_file,
        )
    else:
        from logging.handlers import RotatingFileHandler

        max_bytes = max(1, int(getattr(settings, "log_file_max_bytes", 5 * 1024 * 1024)))
        backup_count = max(0, int(getattr(settings, "log_file_backup_count", 5)))

        try:
            handler = RotatingFileHandler(
                log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
        except (PermissionError, OSError) as exc:
            module_logger.warning(
                "Log rotation disabled for '%s': %s",
                log_file,
                exc,
            )
            return None

    handler.setFormatter(formatter)
    handler.setLevel(file_log_level)
    handler.addFilter(SensitiveDataFilter())
    handler.addFilter(RepeatedNoiseFilter())
    return handler


def _resolve_log_file_path(raw_log_file: Any) -> Path:
    """Resolve configured log file paths relative to the bot_service app root."""
    log_file = Path(str(raw_log_file or "logs/bot_service.log"))
    if log_file.is_absolute():
        return log_file

    app_root = Path(__file__).resolve().parents[1]
    return app_root / log_file


def setup_structured_logging():
    """
    Configure structured logging for the application.
    
    Call this once at application startup, before any logging occurs.
    Idempotent: subsequent calls will be ignored.
    """
    global _SETUP_DONE
    if _SETUP_DONE:
        return
    _SETUP_DONE = True

    _configure_console_streams_for_utf8()

    json_logs_enabled = settings.is_production or getattr(settings, 'enable_json_logs', False)
    log_level = _resolve_log_level(getattr(settings, "log_level", "INFO"), logging.INFO)

    processors: list[Processor] = []

    # Keep explicit level/timestamp enrichment for JSON logs.
    if json_logs_enabled:
        processors.extend([
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
        ])

    processors.extend([
        # Add caller information (file, line, function)
        structlog.processors.CallsiteParameterAdder(
            parameters=[
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.LINENO,
                structlog.processors.CallsiteParameter.FUNC_NAME,
            ]
        ),
        # Add application context
        add_app_context,
    ])

    if json_logs_enabled:
        processors.append(add_severity_level)

    processors.extend([
        # Censor sensitive data
        censor_sensitive_data,
        # Add exception info
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ])
    
    # Choose renderer based on environment
    if json_logs_enabled:
        # JSON for production (machine-readable)
        processors.append(structlog.processors.JSONRenderer())
        structlog.processors.JSONRenderer()
    else:
        # Console for development (human-readable)
        # Keep colors disabled to avoid ANSI escape noise in rotated log files.
        processors.append(structlog.dev.ConsoleRenderer(colors=False))
    
    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            log_level
        ),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Configure standard library logging in a predictable single-line format.
    console_formatter = logging.Formatter(
        fmt="%(asctime)s.%(msecs)03d | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(log_level)

    import io
    utf8_stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    console_handler = logging.StreamHandler(utf8_stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(console_formatter)
    console_handler.addFilter(SensitiveDataFilter())
    console_handler.addFilter(RepeatedNoiseFilter())
    root_logger.addHandler(console_handler)
    
    # Redirect warnings to logging
    logging.captureWarnings(True)

    # Keep uvicorn startup/error logs, but hide verbose access duplicates.
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.WARNING)
    logging.getLogger("watchfiles").setLevel(logging.CRITICAL)
    logging.getLogger("watchfiles.main").setLevel(logging.CRITICAL)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    
    # Setup log rotation if enabled
    if getattr(settings, 'enable_log_rotation', True):
        setup_log_rotation()
    
    logger = structlog.get_logger()
    logger.info(
        "structured_logging_initialized",
        environment=settings.environment,
        json_logs=json_logs_enabled
    )


def setup_log_rotation():
    """
    Setup log file rotation.

    File log level is configurable via settings.log_file_level.
    """
    log_file = _resolve_log_file_path(getattr(settings, 'log_file', 'logs/bot_service.log'))
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError) as exc:
        module_logger.warning(
            "File log rotation disabled because log directory '%s' is not writable: %s",
            log_file.parent,
            exc,
        )
        return

    file_log_level = _resolve_log_level(getattr(settings, "log_file_level", "WARNING"), logging.WARNING)
    handler = _create_file_log_handler(log_file, file_log_level)
    if handler is None:
        return

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)


def get_logger(name: str = None) -> structlog.BoundLogger:
    """
    Get a structured logger instance.
    
    Usage:
        logger = get_logger(__name__)
        logger.info("user_logged_in", user_id=123, platform="twitch")
    
    Args:
        name: Logger name (usually __name__)
    
    Returns:
        Structured logger instance
    """
    return structlog.get_logger(name)


# Context managers for adding context to logs

class LogContext:
    """
    Context manager for adding context to all logs within a block.
    
    Usage:
        with LogContext(user_id=123, platform="twitch"):
            logger.info("processing_request")
            # All logs will include user_id and platform
    """
    
    def __init__(self, **context):
        self.context = context
        self.token = None
    
    def __enter__(self):
        self.token = structlog.contextvars.bind_contextvars(**self.context)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        structlog.contextvars.unbind_contextvars(*self.context.keys())


def bind_context(**context):
    """
    Bind context to all subsequent logs in the current context.
    
    Usage:
        bind_context(user_id=123, platform="twitch")
        logger.info("processing_request")  # Will include user_id and platform
    """
    structlog.contextvars.bind_contextvars(**context)


def unbind_context(*keys):
    """
    Unbind context from logs.
    
    Usage:
        unbind_context("user_id", "platform")
    """
    structlog.contextvars.unbind_contextvars(*keys)


def clear_context():
    """
    Clear all bound context.
    """
    structlog.contextvars.clear_contextvars()


# Convenience functions for common log patterns

def log_request(method: str, path: str, **extra):
    """Log HTTP request"""
    logger = get_logger("http")
    logger.info(
        "http_request",
        method=method,
        path=path,
        **extra
    )


def log_response(method: str, path: str, status_code: int, duration_ms: float, **extra):
    """Log HTTP response"""
    logger = get_logger("http")
    logger.info(
        "http_response",
        method=method,
        path=path,
        status_code=status_code,
        duration_ms=round(duration_ms, 2),
        **extra
    )


def log_error(error: Exception, context: str = None, **extra):
    """Log error with context"""
    logger = get_logger("error")
    logger.error(
        "error_occurred",
        error_type=type(error).__name__,
        error_message=str(error),
        context=context,
        exc_info=True,
        **extra
    )


def log_db_query(query: str, duration_ms: float, **extra):
    """Log database query"""
    logger = get_logger("database")
    logger.debug(
        "db_query",
        query=query[:200],  # Truncate long queries
        duration_ms=round(duration_ms, 2),
        **extra
    )


def log_user_action(action: str, user_id: int, **extra):
    """Log user action"""
    logger = get_logger("user")
    logger.info(
        "user_action",
        action=action,
        user_id=user_id,
        **extra
    )
