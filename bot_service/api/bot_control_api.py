# bot_service/api/bot_control_api.py
"""
API endpoints for bot control.

Refactored to use BotControlService and UserRepository.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth.auth import get_current_user
from core.database import get_db
from repositories.user_repository import UserRepository
from services.bot_control_service import BotControlService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["bot-control"])


def get_bot_control_service() -> BotControlService:
    return BotControlService()


def _get_user_or_404(db: Session, user: dict) -> tuple[int, object]:
    user_id = user.get("id")
    user_repo = UserRepository(db)
    user_record = user_repo.get_by_id(user_id)
    if not user_record:
        raise HTTPException(status_code=404, detail="User not found")
    return user_id, user_record


@router.get("/bot/status")
async def get_bot_status(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    bot_service: BotControlService = Depends(get_bot_control_service),
):
    """Get bot status."""
    try:
        user_id, user_record = _get_user_or_404(db, user)
        return bot_service.get_bot_status(user_id, user_record, db)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting bot status")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/chat/connect")
async def connect_chat(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    bot_service: BotControlService = Depends(get_bot_control_service),
):
    """Connect chat bot."""
    try:
        user_id, user_record = _get_user_or_404(db, user)
        logger.info("Chat connect requested by user %s", user_id)
        return bot_service.connect_chat(user_id, user_record, db)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error connecting chat")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/chat/disconnect")
async def disconnect_chat(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    bot_service: BotControlService = Depends(get_bot_control_service),
):
    """Disconnect chat bot."""
    try:
        user_id, user_record = _get_user_or_404(db, user)
        logger.info("Chat disconnect requested by user %s", user_id)
        return bot_service.disconnect_chat(user_id, user_record, db)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error disconnecting chat")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/chat/status")
async def get_chat_status(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    bot_service: BotControlService = Depends(get_bot_control_service),
):
    """Get chat status."""
    try:
        user_id, user_record = _get_user_or_404(db, user)
        return bot_service.get_chat_status(user_id, user_record, db)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting chat status")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/chat/reconnect")
async def reconnect_chat(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    bot_service: BotControlService = Depends(get_bot_control_service),
):
    """Reconnect chat bot."""
    try:
        user_id, user_record = _get_user_or_404(db, user)
        logger.info("Chat reconnect requested by user %s", user_id)
        return bot_service.reconnect_chat(user_id, user_record, db)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error reconnecting chat")
        raise HTTPException(status_code=500, detail="Internal server error")
