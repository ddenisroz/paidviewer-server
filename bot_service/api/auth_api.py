# bot_service/api/auth_api.py
"""
Authentication API endpoints.
Clean Architecture: uses UserRepository for data access.
"""
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import logging

from core.database import get_db
from core.security_modern import limiter
from core.session_manager import session_manager
from core.cookie_config import get_session_cookie_settings
from core.config import settings

from core.auth_handlers import auth_handlers
from auth.auth import create_jwt_token, get_current_user
from repositories.user_repository import UserRepository
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# Reserved usernames
RESERVED_NAMES = {'admin', 'root', 'system', 'bot', 'moderator', 'mod'}


class DevLoginRequest(BaseModel):
    """Temporary local-development login payload."""

    nickname: str = Field(..., min_length=2, max_length=50)


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get current authenticated user."""
    return current_user


@router.get("/check-username")
@limiter.limit("30/minute")
async def check_username_availability(
    request: Request,
    username: str = Query(..., min_length=3, max_length=25),
    db: Session = Depends(get_db)
):
    """Check whether a username is available."""
    try:
        username_normalized = username.strip().lower()

        # Check reserved names
        if username_normalized in RESERVED_NAMES:
            return {"available": False, "username": username, "reason": "reserved"}

        # Check database
        repo = UserRepository(db)
        if repo.is_username_taken(username):
            return {"available": False, "username": username, "reason": "taken"}

        return {"available": True, "username": username}

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error checking username availability")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/logout")
async def logout(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Logout current user."""
    return await auth_handlers.logout(current_user, db)


@router.post("/dev-login")
async def dev_login(
    payload: DevLoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Temporary local-development login by existing nickname."""
    if not settings.is_development:
        raise HTTPException(status_code=404, detail="Not found")

    nickname = payload.nickname.strip()
    if not nickname:
        raise HTTPException(status_code=400, detail="Введите никнейм")

    repo = UserRepository(db)
    user = (
        repo.get_by_twitch_username(nickname)
        or repo.get_by_vk_username(nickname)
        or repo.get_by_vk_channel_name(nickname)
    )

    if not user:
        raise HTTPException(status_code=404, detail="Пользователь с таким ником не найден")

    if not getattr(user, "is_active", True):
        raise HTTPException(status_code=403, detail="Пользователь отключён")

    if getattr(user, "is_blocked", False):
        blocked_reason = getattr(user, "blocked_reason", None) or "Пользователь заблокирован"
        raise HTTPException(status_code=403, detail=blocked_reason)

    device_info = {
        "platform": "dev-login",
        "login_method": "dev_login",
        "nickname_lookup": nickname,
        "ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }
    session_id = session_manager.create_session(user.id, device_info=device_info)

    response = JSONResponse(
        {
            "success": True,
            "authenticated": True,
            "user": {
                "id": user.id,
                "twitch_username": user.twitch_username,
                "vk_username": user.vk_username,
                "vk_channel_name": user.vk_channel_name,
                "is_admin": bool(user.role == "admin" or user.is_admin),
            },
        }
    )
    response.set_cookie(**get_session_cookie_settings(session_id))
    return response


@router.get("/ws-token")
async def get_websocket_token(current_user: dict = Depends(get_current_user)):
    """Return a short-purpose websocket auth token for dashboard/chat clients."""
    user_id = current_user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required.")

    return {
        "success": True,
        "token": create_jwt_token(int(user_id), token_type="chat_ws"),
        "user_id": int(user_id),
    }


@router.get("/status")
async def auth_status(request: Request, db: Session = Depends(get_db)):
    """Get the current authentication and integration status."""
    logger.info("=== AUTH STATUS REQUEST START ===")
    session_id = request.cookies.get("session_id")
    
    if not session_id:
        logger.info("[AUTH] No session_id found")
        return {"authenticated": False}
    
    session_data = session_manager.validate_session(session_id)
    if not session_data:
        logger.info("[AUTH] Session validation failed")
        return {"authenticated": False, "integrations": {}}
    
    user_id = session_data.get("user_id")
    
    if not user_id or user_id <= 0:
        logger.info("[AUTH] Invalid user_id in session")
        return {"authenticated": False, "integrations": {}}
    
    # Get user
    repo = UserRepository(db)
    user_data = {}
    user = None
    
    try:
        user = repo.get_by_id(user_id)
        if user:
            user_data = {
                "id": user.id,
                "twitch_username": user.twitch_username,
                "vk_username": user.vk_username,
                "vk_channel_name": user.vk_channel_name,
                "is_admin": bool(user.role == "admin" or user.is_admin)
            }
    except Exception:
        logger.exception("[ERROR] Error getting user data")
        user_data = {
            "id": user_id,
            "twitch_username": None,
            "vk_username": None,
            "vk_channel_name": None,
            "is_admin": session_data.get("is_admin", False)
        }
    
    # Get integrations
    integrations = await _get_user_integrations(user_id, user, repo)
    
    logger.info("=== AUTH STATUS REQUEST END ===")
    return {
        "authenticated": True,
        "integrations": integrations,
        "user": user_data
    }


async def _get_user_integrations(user_id: int, user, repo: UserRepository) -> dict:
    """
    Returns user integrations WITHOUT token validation.
    
    OPTIMIZATION: Token validation is skipped to keep page load fast.
    Tokens are validated only when they are actually used by API calls.
    This keeps auth/status latency under ~50ms instead of ~1200ms.
    """
    integrations = {}
    
    try:
        user_tokens = repo.get_user_tokens(user_id)
        
        for token in user_tokens:
            is_active = getattr(token, 'is_active', True)
            if not is_active or not token.access_token:
                continue
            
            # REMOVED: Token validation via HTTP (was causing 1s+ delay)
            # Validation now happens only when token is actually used (e.g., update stream title)
            
            # VK: check it's a streamer OAuth token (not bot token)
            if token.platform == 'vk':
                if not token.refresh_token or not token.scopes:
                    continue
            
            # Get username
            username = None
            if token.platform == 'twitch' and user:
                username = user.twitch_username
            elif token.platform == 'vk' and user:
                username = user.vk_username
            elif token.platform == 'donationalerts' and user:
                username = getattr(user, 'donationalerts_username', None)
            
            integrations[token.platform] = {
                "connected": True,
                "enabled": True,
                "platform_user_id": token.platform_user_id,
                "avatar_url": token.avatar_url,
                "username": username
            }
            
    except Exception:
        logger.exception("[ERROR] Error fetching integrations")
    
    return integrations

