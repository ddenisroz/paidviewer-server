# bot_service/api/admin/users.py
"""
Admin Users API endpoints.

Clean Architecture: endpoints delegate to services.
No direct DB queries in this file.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from core.database import get_db
from auth.auth import get_current_user
from typing import Optional
import logging

from services.admin import get_admin_stats_service, whitelist_service, user_management_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def require_admin(user: dict):
    """Check if user is admin."""
    if not (user.get('role') == 'admin' or user.get('is_admin', False)):
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/users")
async def get_admin_users(
    page: int = 1,
    limit: int = 50,
    search: str = None,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the user list for the admin panel."""
    try:
        require_admin(user)
        
        stats_service = get_admin_stats_service(db)
        result = stats_service.get_admin_users_list(page=page, limit=limit, search=search)
        
        return {"success": True, **result}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting admin users")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/users/{user_id}/block")
async def block_user(
    user_id: int,
    reason: str = None,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Comprehensive user blocking:
    1. Blocks OAuth access (User.is_blocked)
    2. Blocks all user channels in compatibility mode (BlockedChannel)
    3. Disconnects the bot from all user channels
    """
    try:
        require_admin(user)
        
        # Use service for blocking
        result = await user_management_service.block_user(
            user_id, 
            {"reason": reason or "Blocked by administrator"}, 
            db
        )
        
        if "error" in result:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Disconnect bots (runtime operation, stays in controller)
        from startup.bot_registry import get_bot_registry
        from repositories.user_repository import UserRepository
        
        user_repo = UserRepository(db)
        target_user = user_repo.get_by_id(user_id)
        
        disconnected = []
        if target_user:
            registry = get_bot_registry()
            
            if target_user.twitch_username and registry.twitch_bot:
                try:
                    await registry.twitch_bot.part_channels([target_user.twitch_username])
                    disconnected.append(f"Twitch: {target_user.twitch_username}")
                except Exception:
                    logger.exception("Error disconnecting Twitch bot")
            
            if target_user.vk_channel_name and registry.vk_bot:
                try:
                    await registry.vk_bot.disconnect_from_channel(target_user.vk_channel_name)
                    disconnected.append(f"VK: {target_user.vk_channel_name}")
                except Exception:
                    logger.exception("Error disconnecting VK bot")
        
        return JSONResponse(content={
            "success": True,
            "message": f"User {user_id} fully blocked",
            "details": {
                "oauth_blocked": True,
                "bots_disconnected": disconnected,
                "reason": reason or "Blocked by administrator"
            }
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error blocking user")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/users/{user_id}/unblock")
async def unblock_user(
    user_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Perform a comprehensive user unblock."""
    try:
        require_admin(user)
        
        result = await user_management_service.unblock_user(user_id, db)
        
        if "error" in result:
            raise HTTPException(status_code=404, detail="User not found")
        
        return JSONResponse(content={
            "success": True,
            "message": f"User {user_id} fully unblocked",
            "details": {"oauth_unblocked": True}
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error unblocking user")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/sessions")
async def get_sessions(
    page: int = 1,
    limit: int = 50,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the list of active sessions."""
    try:
        require_admin(user)
        
        stats_service = get_admin_stats_service(db)
        result = stats_service.get_sessions_paginated(page=page, limit=limit)
        
        return {"success": True, **result}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting sessions")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/whitelist/add")
async def add_to_whitelist(
    request: Request,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add a user to the whitelist."""
    try:
        require_admin(user)
        
        try:
            body = await request.json()
            username = body.get('username') or body.get('channel_name')
            platform = (body.get('platform') or 'twitch').lower().strip()
        except Exception:
            username = request.query_params.get('username') or request.query_params.get('channel_name')
            platform = (request.query_params.get('platform') or 'twitch').lower().strip()
        
        if not username:
            raise HTTPException(status_code=400, detail="Username or channel_name is required")
        
        username = username.lower().strip()
        if platform not in ("twitch", "vk"):
            platform = "twitch"
        
        from models.pydantic_models import AddToWhitelistRequest
        request_data = AddToWhitelistRequest(username=username, platform=platform)
        
        result = await whitelist_service.add_to_whitelist(request_data, db)
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return JSONResponse(content={"success": True, "message": f"User {username} added to whitelist"})
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error adding to whitelist")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/whitelist")
async def get_whitelist(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the list of whitelisted users."""
    try:
        require_admin(user)
        
        result = await whitelist_service.get_whitelist(db)
        
        whitelist_data = [
            {
                'id': entry.id,
                'channel_name': entry.channel_name,
                'platform': entry.platform,
                'created_at': entry.created_at.isoformat() if entry.created_at else None
            }
            for entry in result.whitelist_users
        ]
        
        return JSONResponse(content={
            "success": True,
            "whitelist": whitelist_data,
            "total": len(whitelist_data)
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting whitelist")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/whitelist/{username}")
async def remove_from_whitelist(
    username: str,
    platform: Optional[str] = Query(None, description="Platform to remove from (twitch or vk)"),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Remove a user from the whitelist."""
    try:
        require_admin(user)
        
        username = username.lower().strip()
        
        if platform:
            platform = platform.lower().strip()
            if platform not in ("twitch", "vk"):
                raise HTTPException(status_code=400, detail="Invalid platform")
        else:
            platform = "twitch"  # Default
        
        from models.pydantic_models import AddToWhitelistRequest
        request_data = AddToWhitelistRequest(username=username, platform=platform)
        
        result = await whitelist_service.remove_from_whitelist(request_data, db)
        
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        
        return JSONResponse(content={"success": True, "message": f"User {username} removed from whitelist"})
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error removing from whitelist")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
