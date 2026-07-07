# bot_service/core/sentry_config.py
"""
Sentry Configuration for Error Tracking

Provides centralized Sentry setup with:
- Environment-based configuration
- Performance monitoring
- User context
- Custom tags and context
- Before-send filtering
"""
import functools
import logging
from typing import Optional, Dict, Any

try:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
except ModuleNotFoundError:  # pragma: no cover - depends on optional local dev deps
    sentry_sdk = None
    FastApiIntegration = None
    LoggingIntegration = None
    SqlalchemyIntegration = None

from core.config import settings

logger = logging.getLogger(__name__)


def before_send(event: Dict[str, Any], hint: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Filter events before sending to Sentry.
    
    Use this to:
    - Filter out sensitive data
    - Skip certain error types
    - Add additional context
    - Modify error messages
    """
    # Don't send events in development unless explicitly enabled
    if settings.is_development and not getattr(settings, 'sentry_debug', False):
        return None
    
    # Filter out specific exceptions
    if 'exc_info' in hint:
        exc_type, exc_value, tb = hint['exc_info']
        
        # Skip common non-critical errors
        if exc_type.__name__ in ['HTTPException', 'ValidationError']:
            # Only send 5xx errors, not 4xx
            if hasattr(exc_value, 'status_code') and exc_value.status_code < 500:
                return None
    
    # Remove sensitive data from request body
    if 'request' in event:
        request = event['request']
        if 'data' in request:
            # Mask sensitive fields
            sensitive_fields = ['password', 'token', 'secret', 'api_key', 'access_token']
            for field in sensitive_fields:
                if field in request['data']:
                    request['data'][field] = '[FILTERED]'
    
    return event


def init_sentry():
    """
    Initialize Sentry SDK with optimal configuration.
    
    Call this once at application startup.
    """
    sentry_dsn = getattr(settings, 'sentry_dsn', None)
    
    if not sentry_dsn:
        logger.debug("Sentry DSN not configured, error tracking disabled")
        return
    if sentry_sdk is None:
        logger.warning("Sentry DSN is configured, but sentry-sdk is not installed; error tracking disabled")
        return
    
    try:
        sentry_sdk.init(
            dsn=sentry_dsn,
            
            # Environment
            environment=settings.environment,
            
            # Release tracking (use git commit hash in production)
            release=getattr(settings, 'sentry_release', 'bot_service@0.03'),
            
            # Performance monitoring
            traces_sample_rate=getattr(settings, 'sentry_traces_sample_rate', 0.1),  # 10% of transactions
            profiles_sample_rate=getattr(settings, 'sentry_profiles_sample_rate', 0.1),  # 10% of transactions
            
            # Integrations
            integrations=[
                # FastAPI integration
                FastApiIntegration(
                    transaction_style="endpoint",  # Group by endpoint, not URL
                ),
                
                # SQLAlchemy integration (track DB queries)
                SqlalchemyIntegration(),
                
                # Logging integration
                LoggingIntegration(
                    level=logging.INFO,  # Capture info and above
                    event_level=logging.ERROR  # Send errors to Sentry
                ),
            ],
            
            # Filtering
            before_send=before_send,
            
            # Additional options
            attach_stacktrace=True,  # Include stack traces
            send_default_pii=False,  # Don't send PII by default
            max_breadcrumbs=50,  # Keep last 50 breadcrumbs
            
            # Debug mode (only in development)
            debug=settings.is_development and getattr(settings, 'sentry_debug', False),
        )
        
        logger.info(f"[SENTRY] Initialized successfully (environment={settings.environment})")
        
    except Exception as e:
        logger.error(f"[SENTRY] Failed to initialize: {e}")


def set_user_context(user_id: int, username: Optional[str] = None, **extra):
    """
    Set user context for Sentry events.
    
    Call this after user authentication to associate errors with users.
    
    Args:
        user_id: User ID
        username: Username (optional)
        **extra: Additional user data
    """
    if sentry_sdk is None:
        return
    sentry_sdk.set_user({
        "id": user_id,
        "username": username,
        **extra
    })


def set_context(key: str, data: Dict[str, Any]):
    """
    Set custom context for Sentry events.
    
    Use this to add additional context to error reports.
    
    Args:
        key: Context key (e.g., "platform", "feature")
        data: Context data
    """
    if sentry_sdk is None:
        return
    sentry_sdk.set_context(key, data)


def add_breadcrumb(message: str, category: str = "default", level: str = "info", **data):
    """
    Add a breadcrumb to track user actions.
    
    Breadcrumbs help understand what led to an error.
    
    Args:
        message: Breadcrumb message
        category: Category (e.g., "auth", "tts", "youtube")
        level: Level (debug, info, warning, error)
        **data: Additional data
    """
    if sentry_sdk is None:
        return
    sentry_sdk.add_breadcrumb(
        message=message,
        category=category,
        level=level,
        data=data
    )


def capture_exception(error: Exception, **extra):
    """
    Manually capture an exception.
    
    Use this for handled exceptions that you still want to track.
    
    Args:
        error: Exception to capture
        **extra: Additional context
    """
    if sentry_sdk is None:
        return
    if extra:
        with sentry_sdk.push_scope() as scope:
            for key, value in extra.items():
                scope.set_extra(key, value)
            sentry_sdk.capture_exception(error)
    else:
        sentry_sdk.capture_exception(error)


def capture_message(message: str, level: str = "info", **extra):
    """
    Capture a message (not an exception).
    
    Use this for important events that aren't errors.
    
    Args:
        message: Message to capture
        level: Level (debug, info, warning, error, fatal)
        **extra: Additional context
    """
    if sentry_sdk is None:
        return
    if extra:
        with sentry_sdk.push_scope() as scope:
            for key, value in extra.items():
                scope.set_extra(key, value)
            sentry_sdk.capture_message(message, level=level)
    else:
        sentry_sdk.capture_message(message, level=level)


# Convenience decorators

def with_sentry_context(**context):
    """
    Decorator to add context to all Sentry events in a function.
    
    Usage:
        @with_sentry_context(feature="tts", platform="twitch")
        def process_tts_request():
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if sentry_sdk is None:
                return func(*args, **kwargs)
            with sentry_sdk.push_scope() as scope:
                for key, value in context.items():
                    scope.set_tag(key, value)
                return func(*args, **kwargs)
        return wrapper
    return decorator
