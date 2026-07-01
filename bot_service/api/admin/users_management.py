# bot_service/api/admin/users_management.py
"""
Admin-only user management endpoints.

Clean Architecture: endpoints delegate to services.
No direct DB queries in this file.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from core.database import get_db
from auth.auth import get_current_user
from core.permissions import require_permission, Permission, require_role, AppRole
from typing import Optional
from pydantic import BaseModel
import logging

from services.admin import get_admin_stats_service, user_management_service
from services.user_cleanup_service import user_cleanup_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])


def _safe_user_error_message(message: str) -> str:
    if message == "User not found":
        return "User not found"
    return "Invalid user management request"


class UserBlockRequest(BaseModel):
    """Request model for blocking a user"""
    reason: str


class UserUpdateRequest(BaseModel):
    """Request model for updating user"""
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None
    role: Optional[str] = None


@router.get("/list")
@require_permission(Permission.VIEW_ALL_SETTINGS)
async def get_all_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get list of all users (admin only).
    
    Requires: VIEW_ALL_SETTINGS permission
    """
    try:
        stats_service = get_admin_stats_service(db)
        
        # Convert skip/limit to page
        page = (skip // limit) + 1
        
        result = stats_service.get_admin_users_list(page=page, limit=limit, search=search)
        
        return {
            "success": True,
            "total": result["pagination"]["total"],
            "users": result["users"],
            "page": page,
            "pages": result["pagination"]["pages"]
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting users list")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{user_id}")
@require_permission(Permission.VIEW_ALL_SETTINGS)
async def get_user_details(
    user_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific user (admin only).
    
    Requires: VIEW_ALL_SETTINGS permission
    """
    try:
        stats_service = get_admin_stats_service(db)
        result = stats_service.get_user_details(user_id)
        
        if not result:
            raise HTTPException(status_code=404, detail="User not found")
        
        return {"success": True, **result}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting user details")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{user_id}/block")
@require_permission(Permission.BLOCK_USERS)
async def block_user(
    user_id: int,
    request: UserBlockRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Block a user (admin only).
    
    Requires: BLOCK_USERS permission
    """
    try:
        result = await user_management_service.block_user(
            user_id, 
            {"reason": request.reason}, 
            db
        )
        
        if "error" in result:
            if result["error"] == "User not found":
                raise HTTPException(status_code=404, detail="User not found")
            raise HTTPException(status_code=400, detail=_safe_user_error_message(result["error"]))
        
        logger.info(f"User {user_id} blocked by admin {current_user.get('id')}: {request.reason}")
        
        return {
            "success": True,
            "message": f"User {user_id} has been blocked"
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error blocking user")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{user_id}/unblock")
@require_permission(Permission.BLOCK_USERS)
async def unblock_user(
    user_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Unblock a user (admin only).
    
    Requires: BLOCK_USERS permission
    """
    try:
        result = await user_management_service.unblock_user(user_id, db)
        
        if "error" in result:
            if result["error"] == "User not found":
                raise HTTPException(status_code=404, detail="User not found")
            raise HTTPException(status_code=400, detail=_safe_user_error_message(result["error"]))
        
        logger.info(f"User {user_id} unblocked by admin {current_user.get('id')}")
        
        return {
            "success": True,
            "message": f"User {user_id} has been unblocked"
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error unblocking user")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{user_id}")
@require_permission(Permission.MANAGE_USERS)
async def update_user(
    user_id: int,
    request: UserUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update user properties (admin only).
    
    Requires: MANAGE_USERS permission
    """
    try:
        update_data = request.model_dump(exclude_unset=True)
        result = await user_management_service.update_user(user_id, update_data, db)
        
        if "error" in result:
            if result["error"] == "User not found":
                raise HTTPException(status_code=404, detail="User not found")
            raise HTTPException(status_code=400, detail=_safe_user_error_message(result["error"]))
        
        logger.info(f"User {user_id} updated by admin {current_user.get('id')}")
        
        return {
            "success": True,
            "message": f"User {user_id} has been updated"
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error updating user")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{user_id}")
@require_role(AppRole.ADMIN)
async def delete_user(
    user_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a user (admin only).
    
    Requires: ADMIN role
    """
    try:
        # Prevent self-deletion
        if user_id == current_user.get('id'):
            raise HTTPException(status_code=403, detail="Cannot delete yourself")
        
        result = await user_cleanup_service.permanently_delete_user(
            user_id,
            db,
            actor_user_id=current_user.get("id"),
        )
        
        logger.warning(f"User {user_id} deleted by admin {current_user.get('id')}")
        
        return {
            "success": True,
            "message": result.message,
            "deleted_data": result.deleted_counts,
        }
    except ValueError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail="User not found")
        raise HTTPException(status_code=400, detail=_safe_user_error_message(str(exc)))
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error deleting user")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/stats/overview")
@require_permission(Permission.VIEW_ALL_SETTINGS)
async def get_stats_overview(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get system statistics overview (admin only).
    
    Requires: VIEW_ALL_SETTINGS permission
    """
    try:
        stats_service = get_admin_stats_service(db)
        
        user_counts = stats_service.get_user_counts()
        message_counts = stats_service.get_message_counts()
        session_counts = stats_service.get_session_counts()
        
        return {
            "success": True,
            "stats": {
                "users": {
                    "total": user_counts["total"],
                    "active": user_counts["active"],
                    "blocked": user_counts["blocked"],
                    "admins": 0,  # Can be added to service if needed
                    "recent_registrations": user_counts["new_this_month"]
                },
                "platforms": {
                    "twitch": 0,  # Can be added to service if needed
                    "vk": 0
                },
                "activity": {
                    "total_messages": message_counts["total"],
                    "active_sessions": session_counts["active"]
                }
            }
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting stats overview")
        raise HTTPException(status_code=500, detail="Internal server error")
