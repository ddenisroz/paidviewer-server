# bot_service/auth.py
import logging
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.security_modern import modern_security_manager as security_manager
from core.session_manager import session_manager
from core.user_cache import user_cache

logger = logging.getLogger(__name__)


def _is_public_token_request(request: Request) -> bool:
    path = request.url.path or ""
    query = request.query_params
    public_token_routes = (
        ("/api/drops/", "widget_token"),
        ("/api/chatbox/", "token"),
        ("/api/youtube/", "token"),
        ("/api/tts/", "dock_token"),
        ("/api/tts/", "obs_token"),
    )
    return any(path.startswith(prefix) and query.get(param) for prefix, param in public_token_routes)


def get_session_data(request: Request) -> Optional[Dict[str, Any]]:
    """Extract and validate session data from the session cookie."""
    if _is_public_token_request(request):
        return None
    session_id = request.cookies.get("session_id")
    if not session_id:
        return None
    return session_manager.validate_session(session_id)


def _extract_authenticated_user_id(session_data: Dict[str, Any]) -> Optional[int]:
    raw_user_id = session_data.get("id") or session_data.get("user_id")
    if raw_user_id in (None, "", False):
        return None

    try:
        user_id = int(raw_user_id)
    except (TypeError, ValueError):
        return None

    return user_id if user_id > 0 else None


async def get_current_user(request: Request, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Return the authenticated user from the database-backed session."""
    if hasattr(request.state, "current_user"):
        return request.state.current_user

    session_data = get_session_data(request)
    if not session_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = _extract_authenticated_user_id(session_data)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_data = user_cache.get(user_id, db)
    if not user_data:
        logger.warning("User %s not found in DB", user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )

    if not user_data.get("is_active", True):
        logger.warning("User %s is not active", user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is inactive.",
        )

    if user_data.get("is_blocked", False):
        logger.warning("User %s is blocked", user_id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account is blocked: {user_data.get('blocked_reason', 'No reason provided')}",
        )

    logger.debug("User authenticated: ID %s, role=%s", user_id, user_data.get("role"))
    request.state.current_user = user_data
    return user_data


async def get_current_user_optional(request: Request, db: Session = Depends(get_db)) -> Optional[Dict[str, Any]]:
    """Return the authenticated user if a valid session exists, otherwise `None`."""
    if hasattr(request.state, "current_user_optional"):
        return request.state.current_user_optional

    if request.query_params.get("widget_token") and request.url.path.startswith("/api/drops/"):
        request.state.current_user_optional = None
        return None

    session_data = get_session_data(request)
    if not session_data:
        request.state.current_user_optional = None
        return None

    user_id = _extract_authenticated_user_id(session_data)
    if not user_id:
        request.state.current_user_optional = None
        return None

    user_data = user_cache.get(user_id, db)
    request.state.current_user_optional = user_data
    return user_data


async def get_admin_user(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Require the current user to have admin role."""
    if not (current_user.get("role") == "admin" or current_user.get("is_admin", False)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator privileges are required.")
    return current_user


def create_jwt_token(user_id: int, token_type: str = "obs") -> str:
    """Create a long-lived JWT token for OBS/widgets."""
    from datetime import datetime, timedelta, timezone
    import secrets

    data = {
        "user_id": user_id,
        "type": token_type,
        "scope": token_type,
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "jti": secrets.token_urlsafe(16),
    }
    expires_delta = timedelta(days=365)
    return security_manager.create_access_token(data, expires_delta)


def verify_jwt_token(token: str, expected_type: Optional[str] = None) -> Dict[str, Any]:
    """Verify and decode a JWT token."""
    return security_manager.verify_jwt_token(token, expected_type)
