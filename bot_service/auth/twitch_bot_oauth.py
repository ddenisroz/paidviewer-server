"""
OAuth authorization for Twitch bot with refresh token support.

Uses full OAuth2 flow instead of legacy TMI token flow.
"""

import logging
import secrets

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
from services.twitch_bot_oauth_service import (
    UnexpectedTwitchBotAccountError,
    twitch_bot_oauth_service,
)

logger = logging.getLogger(__name__)

router = APIRouter()

ADMIN_BOT_PAGE = f"{settings.frontend_url}/dashboard/admin?tab=runtime"


@router.get("/auth/twitch/bot/login")
@limiter.limit(settings.rate_limit_login)
async def login_twitch_bot(request: Request):
    """Start Twitch bot OAuth authorization flow."""
    try:
        session_data, auth_mode = authorize_bot_oauth_login(
            request,
            platform="twitch",
            allow_link_token=True,
        )
        user_id = session_data.get("user_id") if session_data else None

        state = secrets.token_urlsafe(16)
        auth_url = twitch_bot_oauth_service.get_authorization_url(state)

        logger.info(f"[BOT OAUTH] {auth_mode} initiated Twitch bot OAuth (user_id={user_id})")

        response = RedirectResponse(url=auth_url)
        response.set_cookie(
            key="bot_oauth_state",
            value=state,
            max_age=600,  # 10 minutes
            httponly=True,
            secure=settings.environment == "production",
        )
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating bot OAuth URL: {e}")
        raise HTTPException(status_code=500, detail="Failed to start OAuth flow")


@router.get("/api/admin/bot/twitch/login-link")
@limiter.limit(settings.rate_limit_login)
async def create_twitch_bot_login_link(request: Request):
    """Create short-lived Twitch bot OAuth login link for use in another browser/profile."""
    session_data, _ = authorize_bot_oauth_login(request, platform="twitch")
    user_id = session_data.get("user_id")
    if not user_id:
        raise HTTPException(status_code=403, detail="Admin session required")

    token = create_bot_oauth_link_token(user_id, platform="twitch", expires_minutes=10)
    login_url = f"{settings.backend_url}/auth/twitch/bot/login?{BOT_OAUTH_TOKEN_QUERY_PARAM}={token}"

    return {
        "success": True,
        "url": login_url,
        "expires_in_seconds": 600,
    }


@router.get("/auth/twitch/bot/callback")
@limiter.limit("10/minute")
async def twitch_bot_callback(
    request: Request,
    db: Session = Depends(get_db),
    code: str = None,
    state: str = None,
    error: str = None,
    error_description: str = None,
):
    """Handle Twitch bot OAuth callback."""
    logger.info(
        "[BOT OAUTH] Callback received: path=%s has_code=%s has_error=%s",
        request.url.path,
        bool(code),
        bool(error),
    )

    if error:
        logger.warning(f"[BOT OAUTH] OAuth cancelled: {error} - {error_description}")
        return RedirectResponse(url=f"{ADMIN_BOT_PAGE}&platform=twitch&bot_auth_error=cancelled")

    if not code:
        logger.error("[BOT OAUTH] No authorization code received")
        raise HTTPException(status_code=400, detail="No authorization code received")

    saved_state = request.cookies.get("bot_oauth_state")
    if not saved_state or not state or not secrets.compare_digest(saved_state, state):
        logger.error("[BOT OAUTH] Invalid state parameter")
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    access_token = None
    bot_user_id = None
    bot_login = None

    try:
        logger.info("[BOT OAUTH] Exchanging code for tokens...")
        token_data = await twitch_bot_oauth_service.exchange_code_for_token(code)

        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)
        scopes = token_data.get("scope", [])

        logger.info(f"[BOT OAUTH] Token exchange successful. Expires in: {expires_in}s")

        logger.info("[BOT OAUTH] Getting bot user info...")
        bot_info = await twitch_bot_oauth_service.get_bot_user_info(access_token)
        bot_user_id = bot_info.get("id")
        bot_login = bot_info.get("login")

        logger.info(f"[BOT OAUTH] Bot: {bot_login} (ID: {bot_user_id})")
        twitch_bot_oauth_service.assert_expected_bot_identity(bot_user_id, bot_login)

        logger.info("[BOT OAUTH] Saving bot tokens to database...")
        success = await twitch_bot_oauth_service.save_bot_token(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            scopes=scopes,
            bot_user_id=bot_user_id,
            bot_login=bot_login,
            db=db,
        )
        if not success:
            raise Exception("Failed to save bot tokens")

        logger.info("[OK] [BOT OAUTH] Bot tokens saved successfully")

        logger.info("[BOT OAUTH] Restarting Twitch bot with new token...")
        from core.connection_manager import get_connection_manager
        from startup.bot_initializer import initialize_twitch_bot
        from startup.bot_registry import get_bot_registry

        registry = get_bot_registry()
        if registry.is_twitch_running():
            await registry.stop_twitch_bot()
            logger.info("[BOT OAUTH] Old bot stopped")

        connection_manager = get_connection_manager()
        twitch_channels = await connection_manager.get_twitch_channels_for_bot(db)
        await initialize_twitch_bot(twitch_channels)
        logger.info("[OK] [BOT OAUTH] Bot restarted with new token")

        response = RedirectResponse(url=f"{ADMIN_BOT_PAGE}&platform=twitch&bot_auth_success=true")
        response.delete_cookie("bot_oauth_state")
        return response

    except UnexpectedTwitchBotAccountError as error:
        logger.warning(
            "[SECURITY] Rejected Twitch bot OAuth for login=%s user_id=%s: %s",
            bot_login,
            bot_user_id,
            error,
        )
        await twitch_bot_oauth_service.revoke_access_token(access_token)
        response = RedirectResponse(
            url=f"{ADMIN_BOT_PAGE}&platform=twitch&bot_auth_error=unexpected_account"
        )
        response.delete_cookie("bot_oauth_state")
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ERROR] [BOT OAUTH] Error during bot OAuth: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error during bot authentication")


@router.post("/api/admin/bot/refresh-token")
@limiter.limit("5/minute")
async def refresh_bot_token(
    request: Request,
    db: Session = Depends(get_db),
):
    """Force refresh Twitch bot token and restart bot."""
    try:
        session_data, auth_mode = authorize_bot_oauth_login(request, platform="twitch")
        user_id = session_data.get("user_id") if session_data else None
        logger.info(f"[BOT OAUTH] {auth_mode} requested Twitch bot token refresh (user_id={user_id})")

        success = await twitch_bot_oauth_service.refresh_bot_token(db)
        if success:
            logger.info("[OK] [BOT OAUTH] Bot token refreshed successfully")

            from core.connection_manager import get_connection_manager
            from startup.bot_initializer import initialize_twitch_bot
            from startup.bot_registry import get_bot_registry

            registry = get_bot_registry()
            if registry.is_twitch_running():
                await registry.stop_twitch_bot()

            connection_manager = get_connection_manager()
            twitch_channels = await connection_manager.get_twitch_channels_for_bot(db)
            await initialize_twitch_bot(twitch_channels)

            return {
                "success": True,
                "message": "Bot token refreshed and bot restarted",
            }

        return {
            "success": False,
            "message": "Failed to refresh bot token",
        }

    except Exception as e:
        logger.error(f"Error refreshing bot token: {e}")
        raise HTTPException(status_code=500, detail="Failed to refresh bot token")


@router.get("/api/admin/bot/token-status")
@limiter.limit("10/minute")
async def get_bot_token_status(
    request: Request,
    db: Session = Depends(get_db),
):
    """Get Twitch bot token status for admin panel."""
    try:
        authorize_bot_oauth_login(request, platform="twitch")
        bot_token = await twitch_bot_oauth_service.get_bot_token(db)
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
                needs_refresh = seconds_left <= twitch_bot_oauth_service.REFRESH_IF_NEEDED_THRESHOLD_SECONDS

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
            "message": "Bot token not configured. Please authorize the bot.",
        }

    except Exception as e:
        logger.error(f"Error getting bot token status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get bot token status")


@router.get("/api/admin/bot/twitch/token-status")
@limiter.limit("10/minute")
async def get_twitch_bot_token_status(
    request: Request,
    db: Session = Depends(get_db),
):
    """Alias endpoint with explicit platform segment for Twitch bot token status."""
    return await get_bot_token_status(request, db)


@router.post("/api/admin/bot/twitch/refresh-token")
@limiter.limit("5/minute")
async def refresh_twitch_bot_token(
    request: Request,
    db: Session = Depends(get_db),
):
    """Alias endpoint with explicit platform segment for Twitch bot token refresh."""
    return await refresh_bot_token(request, db)
