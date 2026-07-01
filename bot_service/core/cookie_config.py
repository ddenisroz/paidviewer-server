# bot_service/core/cookie_config.py
"""Production-ready cookie configuration helpers."""
import logging
from typing import Optional
from core.config import settings

logger = logging.getLogger(__name__)

def get_cookie_settings(
    key: str,
    value: str,
    httponly: bool = True,
    samesite: str = "lax",
    path: str = "/",
    max_age: Optional[int] = None
) -> dict:
    """
    Return cookie settings with an environment-aware secure flag.
    
    Args:
        key: Cookie key
        value: Cookie value
        httponly: HttpOnly flag
        samesite: SameSite policy
        path: Cookie path
        max_age: Lifetime in seconds
    
    Returns:
        Keyword arguments for ``response.set_cookie()``
    """
    is_production = settings.environment.lower() == "production"

    cookie_settings = {
        "key": key,
        "value": value,
        "httponly": httponly,
        "secure": is_production,  # True only in production
        "samesite": samesite,
        "path": path
    }

    if max_age is not None:
        cookie_settings["max_age"] = max_age

    # Log extra details in development only.
    if not is_production:
        logger.debug(
            f"[COOKIE] Cookie '{key}' settings: "
            f"secure={cookie_settings['secure']}, "
            f"httponly={httponly}, "
            f"samesite={samesite}"
        )

    return cookie_settings


def is_production() -> bool:
    """Return True when the application runs in production."""
    return settings.environment.lower() == "production"


def is_development() -> bool:
    """Return True when the application does not run in production."""
    return not is_production()


# Session cookie constants.
# Sessions are intentionally long-lived and stay valid until explicit logout
# or replacement by a new login from another device.
TEN_YEARS_IN_SECONDS = 10 * 365 * 24 * 60 * 60  # 315360000 seconds
SESSION_MAX_AGE_SECONDS = TEN_YEARS_IN_SECONDS

def get_session_cookie_settings(session_id: str) -> dict:
    """
    Return settings for the session cookie.
    
    Args:
        session_id: Session ID
        
    Returns:
        Keyword arguments for ``response.set_cookie()``
    """
    return get_cookie_settings(
        key="session_id",
        value=session_id,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=SESSION_MAX_AGE_SECONDS
    )


# Log the active mode when the module is imported.
if settings.is_production:
    logger.info("[SECURITY] Running in PRODUCTION mode: cookies.secure=True")
else:
    logger.info(f"[DEV] Running in {settings.environment.upper()} mode: cookies.secure=False")

