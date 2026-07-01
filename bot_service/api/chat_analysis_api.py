# bot_service/api/chat_analysis_api.py
"""
Chat analysis API endpoints.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.auth import get_current_user
from core.database import get_db
from repositories.user_repository import UserRepository
from services.psychology_service import PsychologyService

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat-analysis"])


class ChatAnalysisRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    platform: str = Field(..., pattern="^(twitch|vk)$")
    channel_name: Optional[str] = None


@router.post("/analysis")
async def analyze_chat_user(
    payload: ChatAnalysisRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Run psychology analysis for a user based on chat history."""
    user_id = user.get("id")
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID not found")

    user_repo = UserRepository(db)
    user_record = user_repo.get_by_id(user_id)
    if not user_record:
        raise HTTPException(status_code=404, detail="User not found")

    platform = payload.platform
    channel_name = (payload.channel_name or "").strip()

    if not channel_name:
        if platform == "twitch":
            channel_name = user_record.twitch_username or ""
        else:
            channel_name = user_record.vk_channel_name or user_record.vk_username or ""

    if not channel_name:
        raise HTTPException(status_code=400, detail="Channel name not configured for platform")

    analyzed_by_username = (
        user_record.twitch_username if platform == "twitch" else user_record.vk_username
    ) or user_record.twitch_username or user_record.vk_username or "user"

    service = PsychologyService(db)
    result = await service.analyze_user_psychology(
        target_username=payload.username,
        platform=platform,
        analyzed_by_user_id=user_id,
        analyzed_by_username=analyzed_by_username,
        channel_name=channel_name,
    )

    if not result:
        raise HTTPException(status_code=500, detail="Analysis failed")

    logger.info(f"[CHAT-ANALYSIS] Completed for {payload.username} ({platform})")
    return {
        "success": True,
        "data": {
            "result": result,
            "channel_name": channel_name,
        }
    }
