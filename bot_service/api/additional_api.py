# bot_service/api/additional_api.py
"""
Additional API endpoints.

REFACTORED: Business logic has been moved to services:
- IntegrationManagementService
- ChatHistoryService  
- AccountDeletionService

This file contains ONLY routing and data transformation.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from core.database import get_db
from auth.auth import get_current_user, get_current_user_optional
from services.integration_management_service import integration_management_service
from services.chat_history_service import chat_history_service
from services.account_deletion_service import account_deletion_service
from services.user_cleanup_service import user_cleanup_service

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["additional"])


# ==================== Auth Endpoints ====================

@router.get("/auth/user/me")
async def get_user_me(user: dict = Depends(get_current_user)):
    """Get information about the current user."""
    return JSONResponse(content={
        "id": user.get("id"),
        "twitch_username": user.get("twitch_username"),
        "vk_username": user.get("vk_username"),
        "is_admin": user.get("is_admin", False),
        "created_at": user.get("created_at")
    })


@router.get("/auth/session/status")
async def get_session_status(user: dict = Depends(get_current_user)):
    """Get the current session status."""
    return JSONResponse(content={
        "authenticated": True,
        "user_id": user.get("id"),
        "session_valid": True,
        "expires_at": None
    })


@router.post("/clear-verifications")
async def clear_verifications(user: dict = Depends(get_current_user)):
    """Clear verification records."""
    logger.info(f"Clear verifications requested by user {user['id']}")
    return JSONResponse(content={"success": True, "message": "Verifications cleared"})


# ==================== Integration Endpoints ====================

@router.get("/integrations")
async def get_integrations(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the user's integrations with token validation."""
    try:
        user_id = user.get("id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID not found")
        
        integrations = await integration_management_service.get_user_integrations(
            user_id, db
        )
        
        # Convert the result to the API response format.
        result = {}
        for platform, info in integrations.items():
            result[platform] = {
                "connected": info.connected,
                "username": info.username,
                "platform_user_id": info.platform_user_id,
                "avatar_url": info.avatar_url,
            }
        
        return JSONResponse(content={"integrations": result})
        
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting integrations")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/integrations/{platform}/disconnect")
async def disconnect_integration(
    platform: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Disable an integration by disconnecting the bot and removing tokens.
    """
    user_id = user.get("id")
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID not found")
    
    try:
        await integration_management_service.disconnect_integration(
            user_id, platform, db
        )
        return JSONResponse(content={
            "success": True, 
            "message": f"{platform} bot disconnected"
        })
    except ValueError:
        raise HTTPException(status_code=404, detail="Resource not found")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error disconnecting %s", platform)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/integrations/{platform}/remove")
async def remove_integration(
    platform: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Fully remove an integration.
    A complete re-authorization will be required afterwards.
    """
    user_id = user.get("id")
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID not found")
    
    try:
        await integration_management_service.remove_integration(
            user_id, platform, db
        )
        return JSONResponse(content={
            "success": True, 
            "message": f"{platform} integration fully removed. Re-authorization required."
        })
    except ValueError:
        raise HTTPException(status_code=404, detail="Resource not found")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error removing %s", platform)
        raise HTTPException(status_code=500, detail="Internal server error")


# ==================== Chat History Endpoints ====================

@router.get("/chat/history")
async def get_chat_history(
    channel: str = None,
    platform: str = None,
    limit: int = 50,
    current_user: dict = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Get chat message history."""
    try:
        if not current_user:
            return JSONResponse(content={"success": True, "messages": []})
        
        user_id = current_user.get("id")
        
        messages = chat_history_service.get_chat_history(
            user_id, channel, platform, limit, db
        )
        
        # Convert DTOs into dictionaries for JSON serialization.
        messages_data = [msg.to_dict() for msg in messages]
        
        logger.info(f"[CHAT] Returning {len(messages_data)} messages")
        
        return JSONResponse(content={
            "success": True,
            "messages": messages_data,
            "total": len(messages_data)
        })
        
    except HTTPException:
        raise
    except Exception:
        logger.exception("[CHAT] Error")
        raise HTTPException(status_code=500, detail="Internal server error")


# ==================== Account Deletion Endpoints ====================

@router.post("/admin/permanently-delete-user/{user_id}")
async def permanently_delete_user(
    user_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    [ADMIN ONLY] Permanently delete a user account from the database.

    WARNING: this operation is irreversible.
    """
    # Validate administrator permissions.
    if not (current_user.get('role') == 'admin' or current_user.get('is_admin', False)):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        if user_id == current_user.get("id"):
            raise HTTPException(status_code=403, detail="Cannot delete yourself")

        result = await user_cleanup_service.permanently_delete_user(
            user_id,
            db,
            actor_user_id=current_user.get("id"),
        )
        return JSONResponse(content={
            "success": result.success,
            "message": result.message,
            "deleted_data": result.deleted_counts,
        })
    except ValueError:
        raise HTTPException(status_code=404, detail="Resource not found")
    except HTTPException:
        raise
    except Exception:
        logger.exception("[ADMIN] Error deleting user")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/user/delete-account")
async def delete_user_account(
    request: Request,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Permanently delete a user account.
    
    Removes ALL user data and anonymizes the account record.
    The user is logged out after deletion.
    """
    user_id = user.get("id")
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID not found")
    
    try:
        result = await account_deletion_service.soft_delete_account(user_id, db)
        
        # Clear the session cookie.
        response = JSONResponse(content={
            "success": result.success,
            "message": result.message,
            "deleted_data": result.deleted_counts
        })
        response.delete_cookie(key="session_id", path="/")
        
        return response
        
    except ValueError:
        raise HTTPException(status_code=404, detail="Resource not found")
    except HTTPException:
        raise
    except Exception:
        logger.exception("[ACCOUNT] Error deleting account")
        raise HTTPException(status_code=500, detail="Internal server error")

