"""TTS blocked users routes."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth.auth import get_current_user
from core.database import get_db
from services.tts.tts_core import BlockUserRequest, UnblockUserRequest
from services.tts.tts_service import (
    BlockTargetNotFoundError,
    BlockTargetVerificationUnavailableError,
    TTSService,
)
from services.user_identity_service import UserIdentityService

logger = logging.getLogger("bot_service")

blocked_users_router = APIRouter(prefix="/api/tts", tags=["tts-blocked-users"])


def _resolve_channel_name(current_user: dict, platform: str, explicit_channel_name: Optional[str]) -> Optional[str]:
    if explicit_channel_name:
        return explicit_channel_name.strip()

    if platform == "twitch":
        return (current_user.get("twitch_username") or current_user.get("username") or "").strip() or None

    if platform == "vk":
        return (
            current_user.get("vk_username")
            or current_user.get("vk_channel_name")
            or current_user.get("username")
            or ""
        ).strip() or None

    return None


def _resolve_identity(current_user: dict) -> int:
    user_id = current_user.get("id")
    if user_id in (None, "", False):
        raise HTTPException(status_code=400, detail="Invalid user data")

    try:
        normalized_user_id = int(user_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid user data") from exc

    if normalized_user_id <= 0:
        raise HTTPException(status_code=400, detail="Invalid user data")

    return normalized_user_id


@blocked_users_router.get("/blocked-users")
async def get_blocked_users(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get blocked users list."""
    try:
        if not UserIdentityService.validate_user_data(current_user):
            raise HTTPException(status_code=400, detail="Invalid user data")

        tts_service = TTSService(db)
        user_id = _resolve_identity(current_user)
        blocked_users = await tts_service.get_blocked_users(user_id=user_id)
        return {"success": True, "data": blocked_users}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting blocked users")
        raise HTTPException(status_code=500, detail="Failed to load blocked users")


@blocked_users_router.post("/block")
async def block_user(
    request: BlockUserRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Block a user from TTS."""
    try:
        tts_service = TTSService(db)
        user_id = _resolve_identity(current_user)
        channel_name = _resolve_channel_name(current_user, request.platform, request.channel_name)
        normalized_username = tts_service.normalize_blocked_username(request.username)

        if not channel_name:
            raise HTTPException(status_code=400, detail="Failed to resolve channel_name")

        if tts_service.blocked_user_repo.is_blocked(
            channel_name=channel_name,
            platform=request.platform,
            username=normalized_username,
            user_id=user_id,
        ):
            return {
                "success": True,
                "message": f"User {normalized_username} is already blocked",
                "already_blocked": True,
            }

        validated_username = await tts_service.ensure_block_target_exists(
            user_id=user_id,
            channel_name=channel_name,
            platform=request.platform,
            username=normalized_username,
        )

        success = await tts_service.block_user(
            user_id=user_id,
            channel_name=channel_name,
            platform=request.platform,
            username=validated_username,
        )

        if success:
            return {"success": True, "message": f"User {validated_username} blocked"}

        raise HTTPException(status_code=400, detail="Failed to block user")
    except BlockTargetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BlockTargetVerificationUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error blocking user")
        raise HTTPException(status_code=500, detail="Failed to block user")


@blocked_users_router.post("/unblock")
async def unblock_user(
    request: UnblockUserRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Unblock a user from TTS."""
    try:
        tts_service = TTSService(db)
        user_id = _resolve_identity(current_user)
        channel_name = _resolve_channel_name(current_user, request.platform, request.channel_name)

        if not channel_name:
            raise HTTPException(status_code=400, detail="Failed to resolve channel_name")

        success = await tts_service.unblock_user(
            user_id=user_id,
            channel_name=channel_name,
            platform=request.platform,
            username=request.username,
        )

        if success:
            return {"success": True, "message": f"User {request.username} unblocked"}

        raise HTTPException(status_code=400, detail="Failed to unblock user")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error unblocking user")
        raise HTTPException(status_code=500, detail="Failed to unblock user")


@blocked_users_router.get("/blocked")
async def get_blocked_users_list(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Alias for get blocked users."""
    return await get_blocked_users(current_user, db)


@blocked_users_router.post("/blocked")
async def add_blocked_user(
    request: BlockUserRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Alias for block user."""
    return await block_user(request, current_user, db)


@blocked_users_router.delete("/blocked/{blocked_user_id}")
async def remove_blocked_user(
    blocked_user_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete blocked user by id."""
    try:
        tts_service = TTSService(db)
        user_id = _resolve_identity(current_user)
        success = await tts_service.remove_blocked_user_by_id(user_id, blocked_user_id)
        if success:
            return {"success": True, "message": "Blocked user removed"}

        raise HTTPException(status_code=404, detail="Record not found")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error removing blocked user")
        raise HTTPException(status_code=500, detail="Failed to remove blocked user")

