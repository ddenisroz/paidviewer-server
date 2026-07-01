"""Access helpers for bot OAuth endpoints."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException, Request

from auth.auth import get_session_data
from core.security_modern import modern_security_manager


BOT_OAUTH_TOKEN_TYPE = "bot_oauth_link"
BOT_OAUTH_TOKEN_QUERY_PARAM = "bot_oauth_token"
BOT_OAUTH_TOKEN_HEADER = "X-Bot-OAuth-Token"


def create_bot_oauth_link_token(user_id: int, platform: str, expires_minutes: int = 10) -> str:
    """Create short-lived token for bot OAuth login link."""
    payload = {
        "user_id": user_id,
        "is_admin": True,
        "type": BOT_OAUTH_TOKEN_TYPE,
        "platform": platform,
    }
    return modern_security_manager.create_access_token(payload, timedelta(minutes=expires_minutes))


def _get_bot_oauth_token_from_request(request: Request) -> Optional[str]:
    """Extract bot OAuth link token from query or header."""
    query_token = request.query_params.get(BOT_OAUTH_TOKEN_QUERY_PARAM)
    if query_token:
        return query_token

    header_token = request.headers.get(BOT_OAUTH_TOKEN_HEADER)
    if header_token:
        return header_token

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split("Bearer ", 1)[1].strip()

    return None


def _verify_bot_oauth_link_token(token: str, platform: str) -> Optional[Dict[str, Any]]:
    """Verify bot OAuth link token payload."""
    try:
        payload = modern_security_manager.verify_token(token)
    except HTTPException:
        return None

    if payload.get("type") != BOT_OAUTH_TOKEN_TYPE:
        return None
    if payload.get("platform") != platform:
        return None
    if not payload.get("is_admin", False):
        return None

    user_id = payload.get("user_id")
    if not isinstance(user_id, int) or user_id <= 0:
        return None

    return {"user_id": user_id, "is_admin": True}


def authorize_bot_oauth_login(
    request: Request,
    platform: str,
    allow_link_token: bool = False,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Authorize access to bot OAuth login endpoint.

    Allowed mode:
    - Admin session (`session_id` cookie)
    """
    session_data = get_session_data(request)
    if session_data and session_data.get("is_admin", False):
        return session_data, "admin_session"

    if allow_link_token:
        token = _get_bot_oauth_token_from_request(request)
        if token:
            payload = _verify_bot_oauth_link_token(token, platform)
            if payload:
                return payload, "admin_link_token"

    raise HTTPException(
        status_code=403,
        detail=(
            f"Admin access required for {platform} bot OAuth. "
            "Login as app admin first or use a valid one-time bot OAuth link."
        ),
    )
