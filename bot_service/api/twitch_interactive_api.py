"""Twitch interactive API (hype train and clips)."""

from typing import Any, Optional

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from auth.auth import get_current_user
from core.config import settings

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/twitch/interactive", tags=["twitch-interactive"])


def _extract_user_id(user: Any) -> int:
    if not isinstance(user, dict):
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = user.get("id")
    if not isinstance(user_id, int) or user_id <= 0:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_id


async def get_twitch_credentials(user: dict) -> tuple[str, str, int]:
    from core.database import get_db
    from core.token_encryption import decrypt_token, is_token_encrypted
    from repositories.user_token_repository import UserTokenRepository

    user_id = _extract_user_id(user)
    db = next(get_db())
    try:
        token_repo = UserTokenRepository(db)
        user_token = token_repo.get_by_user_and_platform(user_id, "twitch")
        if not user_token or not user_token.access_token:
            logger.error("twitch_token_not_found", user_id=user_id)
            raise HTTPException(status_code=400, detail="Twitch OAuth token not found")

        token = user_token.access_token
        if is_token_encrypted(token):
            token = decrypt_token(token)

        broadcaster_id = str(user_token.platform_user_id or "").strip()
        if not broadcaster_id:
            logger.error("twitch_broadcaster_id_missing", user_id=user_id)
            raise HTTPException(status_code=400, detail="Twitch broadcaster id not found")

        return token, broadcaster_id, user_id
    finally:
        db.close()


async def make_twitch_api_request(
    method: str,
    endpoint: str,
    token: str,
    *,
    json_data: Optional[dict] = None,
    params: Optional[dict] = None,
) -> dict:
    url = f"https://api.twitch.tv/helix{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Client-Id": settings.twitch_client_id,
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                json=json_data,
                params=params,
                timeout=30.0,
            )

        if response.status_code in {200, 202}:
            return response.json()

        error_data = response.json() if response.text else {}
        error_message = error_data.get("message", "Unknown error")
        logger.error("twitch_api_error", endpoint=endpoint, status_code=response.status_code, error=error_message)
        raise HTTPException(status_code=response.status_code, detail=f"Twitch API error: {error_message}")
    except httpx.RequestError as exc:
        logger.error("twitch_api_request_error", endpoint=endpoint, error=str(exc))
        raise HTTPException(status_code=500, detail="Twitch API connection error")


@router.get("/hype-train", response_model=dict)
async def get_hype_train_events(
    first: int = Query(default=1, ge=1, le=100, description="Number of records"),
    current_user: dict = Depends(get_current_user),
):
    try:
        token, broadcaster_id, user_id = await get_twitch_credentials(current_user)
        response = await make_twitch_api_request(
            "GET",
            "/hypetrain/events",
            token,
            params={"broadcaster_id": broadcaster_id, "first": first},
        )
        events = response.get("data", [])
        pagination = response.get("pagination", {})
        logger.info("twitch_hype_train_fetched", user_id=user_id, events_count=len(events))
        return {"success": True, "events": events, "pagination": pagination}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("twitch_hype_train_fetch_error", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to load Hype Train")


@router.get("/hype-train/current", response_model=dict)
async def get_current_hype_train(current_user: dict = Depends(get_current_user)):
    try:
        token, broadcaster_id, user_id = await get_twitch_credentials(current_user)
        response = await make_twitch_api_request(
            "GET",
            "/hypetrain/events",
            token,
            params={"broadcaster_id": broadcaster_id, "first": 1},
        )
        events = response.get("data", [])

        active_event = None
        if events:
            event = events[0]
            if not event.get("event_data", {}).get("ended_at"):
                active_event = event

        if active_event:
            logger.info(
                "twitch_hype_train_active",
                user_id=user_id,
                event_id=active_event.get("id"),
                level=active_event.get("event_data", {}).get("level"),
            )
        else:
            logger.info("twitch_hype_train_not_active", user_id=user_id)

        return {"success": True, "is_active": active_event is not None, "event": active_event}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("twitch_hype_train_current_error", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to load current Hype Train")


@router.post("/clips/create", response_model=dict)
async def create_clip(
    has_delay: bool = Query(default=False, description="Delay clip creation"),
    current_user: dict = Depends(get_current_user),
):
    try:
        token, broadcaster_id, user_id = await get_twitch_credentials(current_user)
        params = {"broadcaster_id": broadcaster_id}
        if has_delay:
            params["has_delay"] = "true"

        logger.info("twitch_clip_creating", user_id=user_id, has_delay=has_delay)
        response = await make_twitch_api_request("POST", "/clips", token, params=params)
        clip_data = response.get("data", [{}])[0]
        logger.info("twitch_clip_created", user_id=user_id, clip_id=clip_data.get("id"), edit_url=clip_data.get("edit_url"))
        return {
            "success": True,
            "clip": clip_data,
            "message": "Clip creation started. It can take a few seconds before it becomes available.",
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("twitch_clip_create_error", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to create clip")


@router.get("/clips", response_model=dict)
async def get_clips(
    first: int = Query(default=20, ge=1, le=100, description="Number of clips"),
    started_at: Optional[str] = Query(default=None, description="RFC3339 start time"),
    ended_at: Optional[str] = Query(default=None, description="RFC3339 end time"),
    current_user: dict = Depends(get_current_user),
):
    try:
        token, broadcaster_id, user_id = await get_twitch_credentials(current_user)
        params = {"broadcaster_id": broadcaster_id, "first": first}
        if started_at:
            params["started_at"] = started_at
        if ended_at:
            params["ended_at"] = ended_at

        response = await make_twitch_api_request("GET", "/clips", token, params=params)
        clips = response.get("data", [])
        pagination = response.get("pagination", {})
        logger.info("twitch_clips_fetched", user_id=user_id, clips_count=len(clips))
        return {"success": True, "clips": clips, "pagination": pagination}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("twitch_clips_fetch_error", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to load clips")
