# bot_service/auth/vk_bot_oauth.py
"""
OAuth authorization for VK Live bot with refresh token support.
"""

import logging
import re
import secrets
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from auth.bot_oauth_access import (
    BOT_OAUTH_TOKEN_QUERY_PARAM,
    authorize_bot_oauth_login,
    create_bot_oauth_link_token,
)
from core.config import settings
from core.database import get_db
from core.security_modern import limiter
from services.vk_bot_oauth_service import vk_bot_oauth_service

logger = logging.getLogger(__name__)

router = APIRouter()

ADMIN_BOT_PAGE = f"{settings.frontend_url}/dashboard/admin?tab=runtime"
_BOT_AUTH_ERROR_SANITIZER = re.compile(r"[^a-z0-9]+")


def _normalize_bot_auth_error(error: str | None, fallback: str = "internal_error") -> str:
    """Normalize provider/runtime error into a stable UI-safe code."""
    if not error:
        return fallback

    normalized = _BOT_AUTH_ERROR_SANITIZER.sub("_", error.strip().lower()).strip("_")
    return normalized or fallback


def _build_admin_redirect(*, success: bool = False, error: str | None = None) -> RedirectResponse:
    """Redirect back to the admin bots page with a stable auth result code."""
    base_url = f"{ADMIN_BOT_PAGE}&platform=vk"
    redirect_url = f"{base_url}&bot_auth_success=true" if success else (
        f"{base_url}&bot_auth_error={quote(_normalize_bot_auth_error(error))}"
    )

    response = RedirectResponse(url=redirect_url)
    response.delete_cookie("vk_bot_oauth_state")
    return response


@router.get("/auth/vk/bot/login")
@limiter.limit(settings.rate_limit_login)
async def login_vk_bot(request: Request):
    """Start VK Live bot OAuth authorization flow."""
    try:
        session_data, auth_mode = authorize_bot_oauth_login(
            request,
            platform="vk",
            allow_link_token=True,
        )
        user_id = session_data.get("user_id") if session_data else None

        state = secrets.token_urlsafe(16)
        auth_url = vk_bot_oauth_service.get_authorization_url(state)

        logger.info(f"[VK BOT OAUTH] {auth_mode} initiated VK bot OAuth (user_id={user_id})")

        response = RedirectResponse(url=auth_url)
        response.set_cookie(
            key="vk_bot_oauth_state",
            value=state,
            max_age=600,
            httponly=True,
            samesite="lax",
            secure=settings.is_production,
        )
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating VK bot OAuth URL: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/api/admin/bot/vk/login-link")
@limiter.limit(settings.rate_limit_login)
async def create_vk_bot_login_link(request: Request):
    """Create short-lived VK bot OAuth login link for use in another browser/profile."""
    session_data, _ = authorize_bot_oauth_login(request, platform="vk")
    user_id = session_data.get("user_id")
    if not user_id:
        raise HTTPException(status_code=403, detail="Admin session required")

    token = create_bot_oauth_link_token(user_id, platform="vk", expires_minutes=10)
    login_url = f"{settings.backend_url}/auth/vk/bot/login?{BOT_OAUTH_TOKEN_QUERY_PARAM}={token}"

    return {
        "success": True,
        "url": login_url,
        "expires_in_seconds": 600,
    }


@router.get("/auth/vk/bot/callback")
@limiter.limit("10/minute")
async def vk_bot_callback(
    request: Request,
    db: Session = Depends(get_db),
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
):
    """Handle VK Live bot OAuth callback."""
    logger.info(
        "[VK BOT OAUTH] Callback received: path=%s has_code=%s has_error=%s",
        request.url.path,
        bool(code),
        bool(error),
    )

    if error:
        logger.warning(f"[VK BOT OAUTH] OAuth cancelled: {error} - {error_description}")
        return _build_admin_redirect(error=error)

    if not code:
        logger.error("[VK BOT OAUTH] No authorization code received")
        return _build_admin_redirect(error="missing_code")

    saved_state = request.cookies.get("vk_bot_oauth_state")
    if not saved_state or saved_state != state:
        logger.error("[VK BOT OAUTH] Invalid state parameter")
        return _build_admin_redirect(error="invalid_state")

    try:
        logger.info("[VK BOT OAUTH] Exchanging code for tokens...")
        token_data = await vk_bot_oauth_service.exchange_code_for_token(code)

        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)

        scope_str = token_data.get("scope", "")
        scopes = scope_str.split(" ") if scope_str else []

        logger.info(f"[VK BOT OAUTH] Token exchange successful. Expires in: {expires_in}s")

        logger.info("[VK BOT OAUTH] Getting bot user info...")
        bot_info = await vk_bot_oauth_service.get_bot_user_info(access_token)
        bot_user_id = bot_info.get("id")
        bot_login = bot_info.get("login")

        logger.info(f"[VK BOT OAUTH] Bot: {bot_login} (ID: {bot_user_id})")

        logger.info("[VK BOT OAUTH] Saving bot tokens to database...")
        success = await vk_bot_oauth_service.save_bot_token(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            scopes=scopes,
            bot_user_id=bot_user_id,
            bot_login=bot_login,
            db=db,
        )
        if not success:
            logger.error("[VK BOT OAUTH] Failed to save VK bot tokens")
            return _build_admin_redirect(error="save_failed")

        logger.info("[OK] [VK BOT OAUTH] Bot tokens saved successfully")

        logger.info("[VK BOT OAUTH] Restarting VK bot with new token...")
        from startup.bot_initializer import initialize_vk_bot
        from startup.bot_registry import get_bot_registry
        from core.connection_manager import get_connection_manager

        registry = get_bot_registry()
        connection_manager = get_connection_manager()
        vk_channels = await connection_manager.get_vk_channels_for_bot(db)

        if registry.is_vk_running():
            await registry.stop_vk_bot()
            logger.info("[VK BOT OAUTH] Old bot stopped")

        started = await initialize_vk_bot(vk_channels)
        if not started:
            logger.error("[VK BOT OAUTH] Bot token saved, but VK bot restart failed")
            return _build_admin_redirect(error="restart_failed")

        logger.info("[OK] [VK BOT OAUTH] Bot restarted with new token")

        return _build_admin_redirect(success=True)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ERROR] [VK BOT OAUTH] Error during bot OAuth: {e}", exc_info=True)
        return _build_admin_redirect(error="internal_error")


@router.get("/api/admin/bot/vk/token-status")
@limiter.limit("10/minute")
async def get_vk_bot_token_status(
    request: Request,
    db: Session = Depends(get_db),
):
    """Get VK bot token status."""
    try:
        authorize_bot_oauth_login(request, platform="vk")
        bot_token = await vk_bot_oauth_service.get_bot_token(db)

        if bot_token:
            from core.datetime_utils import utcnow_naive

            expires_at = bot_token.get("expires_at")
            days_left = None
            hours_left = None
            seconds_left = None
            needs_refresh = False

            if expires_at:
                seconds_left = max(0, int((expires_at - utcnow_naive()).total_seconds()))
                days_left = seconds_left // 86400
                hours_left = seconds_left // 3600
                needs_refresh = seconds_left <= vk_bot_oauth_service.REFRESH_IF_NEEDED_THRESHOLD_SECONDS

            return {
                "success": True,
                "configured": True,
                "type": "oauth",
                "bot_login": bot_token.get("bot_login"),
                "bot_user_id": bot_token.get("bot_user_id"),
                "expires_at": expires_at.isoformat() if expires_at else None,
                "days_left": days_left,
                "hours_left": hours_left,
                "seconds_left": seconds_left,
                "needs_refresh": needs_refresh,
                "has_refresh_token": bool(bot_token.get("refresh_token")),
            }

        return {
            "success": False,
            "configured": False,
            "message": "Bot token not configured.",
        }
    except Exception as e:
        logger.error(f"Error getting VK bot token status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api/admin/bot/vk/refresh-token")
@limiter.limit("5/minute")
async def refresh_vk_bot_token(
    request: Request,
    db: Session = Depends(get_db),
):
    """Force refresh VK bot token and restart VK bot."""
    try:
        session_data, auth_mode = authorize_bot_oauth_login(request, platform="vk")
        user_id = session_data.get("user_id") if session_data else None
        logger.info(f"[VK BOT OAUTH] {auth_mode} requested VK bot token refresh (user_id={user_id})")

        success = await vk_bot_oauth_service.refresh_bot_token(db)
        if not success:
            return {
                "success": False,
                "message": "Failed to refresh VK bot token",
            }

        from startup.bot_initializer import initialize_vk_bot
        from startup.bot_registry import get_bot_registry
        from core.connection_manager import get_connection_manager

        registry = get_bot_registry()
        connection_manager = get_connection_manager()
        vk_channels = await connection_manager.get_vk_channels_for_bot(db)

        if registry.is_vk_running():
            await registry.stop_vk_bot()

        started = await initialize_vk_bot(vk_channels)
        if not started:
            return {
                "success": False,
                "message": "VK bot token refreshed, but VK bot restart failed",
            }

        return {
            "success": True,
            "message": "VK bot token refreshed and bot restarted",
        }
    except Exception as e:
        logger.error(f"Error refreshing VK bot token: {e}")
        raise HTTPException(status_code=500, detail="Failed to refresh VK bot token")
