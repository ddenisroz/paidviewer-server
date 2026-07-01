"""
Admin Blocked Channels API.
Clean Architecture: uses BlockedChannelRepository for data access.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from core.database import get_db
from auth.auth import get_current_user
from repositories.blocked_channel_repository import BlockedChannelRepository
from typing import Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _channel_to_dict(channel) -> dict:
    """Convert blocked channel model to dict for response."""
    return {
        "id": channel.id,
        "channel_name": channel.channel_name,
        "reason": channel.reason,
        "blocked_by": channel.blocked_by,
        "is_active": channel.is_active,
        "created_at": channel.created_at.isoformat() if channel.created_at else None
    }


@router.get("/blocked-channels")
async def get_blocked_channels(
    page: int = 1,
    limit: int = 50,
    search: str = None,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the list of blocked channels."""
    try:
        if not (user.get('role') == 'admin' or user.get('is_admin', False)):
            raise HTTPException(status_code=403, detail="Admin access required")
        
        repo = BlockedChannelRepository(db)
        blocked_channels, total = repo.get_active_paginated(search=search, page=page, limit=limit)
        
        return {
            "success": True,
            "blocked_channels": [_channel_to_dict(bc) for bc in blocked_channels],
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": (total + limit - 1) // limit if limit > 0 else 0
            }
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting blocked channels")
        raise HTTPException(status_code=500, detail="Failed to fetch blocked channels.")


@router.post("/blocked-channels")
async def block_channel(
    channel_name: str,
    reason: Optional[str] = None,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Block a channel."""
    try:
        if not (user.get('role') == 'admin' or user.get('is_admin', False)):
            raise HTTPException(status_code=403, detail="Admin access required")
        
        # Validate the request.
        if not channel_name or len(channel_name.strip()) < 2:
            raise HTTPException(status_code=400, detail="Channel name must contain at least 2 characters.")
        
        repo = BlockedChannelRepository(db)
        
        # Check whether the channel is already blocked.
        if repo.is_blocked(channel_name):
            raise HTTPException(status_code=400, detail=f"Channel {channel_name} is already blocked")
        
        blocked_channel = repo.block(
            channel_name=channel_name,
            reason=reason,
            blocked_by=user.get('username')
        )
        
        logger.info("[BLOCKED] Blocked channel: %s by %s (reason: %s)", channel_name, user.get("username"), reason)
        
        return {
            "success": True,
            "channel_id": blocked_channel.id,
            "message": f"Channel {channel_name} has been blocked"
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error blocking channel")
        raise HTTPException(status_code=500, detail="Failed to block the channel.")


@router.patch("/blocked-channels/{channel_id}")
async def update_blocked_channel(
    channel_id: int,
    reason: Optional[str] = None,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update blocked channel metadata."""
    try:
        if not (user.get('role') == 'admin' or user.get('is_admin', False)):
            raise HTTPException(status_code=403, detail="Admin access required")
        
        repo = BlockedChannelRepository(db)
        
        if reason:
            channel = repo.update_reason(channel_id, reason)
            if not channel:
                raise HTTPException(status_code=404, detail="Blocked channel not found")
            
            logger.info("[ADMIN] Updated blocked channel: %s", channel.channel_name)
        
        return {
            "success": True,
            "message": "Blocked channel updated"
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error updating blocked channel")
        raise HTTPException(status_code=500, detail="Failed to update the blocked channel.")


@router.delete("/blocked-channels/{channel_id}")
async def unblock_channel(
    channel_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Unblock a channel (soft delete)."""
    try:
        if not (user.get('role') == 'admin' or user.get('is_admin', False)):
            raise HTTPException(status_code=403, detail="Admin access required")
        
        repo = BlockedChannelRepository(db)
        channel = repo.unblock(channel_id)
        
        if not channel:
            raise HTTPException(status_code=404, detail="Blocked channel not found")
        
        logger.info("[OK] Unblocked channel: %s by %s", channel.channel_name, user.get("username"))
        
        return {
            "success": True,
            "message": f"Channel {channel.channel_name} has been unblocked"
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error unblocking channel")
        raise HTTPException(status_code=500, detail="Failed to unblock the channel.")

