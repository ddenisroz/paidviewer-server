# bot_service/api/stream_history_api.py
"""
API for stream history.
Clean Architecture: uses ChatMessageRepository for data access.
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from core.database import get_db
from auth.auth import get_current_user
from repositories.chat_message_repository import ChatMessageRepository
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stream", tags=["stream"])


def _message_to_dict(msg) -> dict:
    """Convert message to dict for response."""
    return {
        'id': msg.id,
        'channel_name': msg.channel_name,
        'platform': msg.platform,
        'viewer_name': getattr(msg, 'viewer_name', 'unknown'),
        'message': msg.message,
        'timestamp': msg.timestamp.isoformat() if msg.timestamp else None,
        'is_tts_enabled': getattr(msg, 'is_tts_enabled', False),
        'tts_processed': getattr(msg, 'tts_processed', False)
    }


@router.get("/history")
async def get_stream_history(
    page: int = Query(default=1, ge=1, le=10_000),
    limit: int = Query(default=100, ge=1, le=500),
    channel_name: str = None,
    platform: str = None,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get stream and chat history."""
    try:
        user_id = user.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Unauthorized")

        repo = ChatMessageRepository(db)
        
        try:
            messages, total_messages = repo.get_paginated(
                user_id=user_id,
                channel_name=channel_name,
                platform=platform,
                page=page,
                limit=limit
            )
        except Exception:
            logger.exception("[WARN] Database error")
            raise HTTPException(status_code=500, detail="Database error")

        return {
            "success": True,
            "messages": [_message_to_dict(msg) for msg in messages],
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total_messages,
                "pages": (total_messages + limit - 1) // limit
            }
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting stream history")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/stats")
async def get_stream_stats(
    channel_name: str = None,
    platform: str = None,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get stream statistics."""
    try:
        user_id = user.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Unauthorized")

        repo = ChatMessageRepository(db)
        stats = repo.get_stats(user_id=user_id, channel_name=channel_name, platform=platform)
        
        return {
            "success": True,
            "stats": stats
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting stream stats")
        raise HTTPException(status_code=500, detail="Internal server error")
