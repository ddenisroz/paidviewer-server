"""Twitch polls API."""

from typing import Any, List, Literal, Optional

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from auth.auth import get_current_user
from core.config import settings

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/twitch/polls", tags=["twitch-polls"])


class PollChoice(BaseModel):
    title: str = Field(..., min_length=1, max_length=25, description="Choice title")


class PollCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=60, description="Poll title")
    choices: List[PollChoice] = Field(..., min_length=2, max_length=5, description="Poll choices")
    duration: int = Field(..., ge=15, le=1800, description="Duration in seconds")
    channel_points_voting_enabled: bool = Field(default=False)
    channel_points_per_vote: Optional[int] = Field(default=None, ge=1, le=1_000_000)

    @field_validator("choices")
    @classmethod
    def validate_choices(cls, values: List[PollChoice]) -> List[PollChoice]:
        titles = [choice.title for choice in values]
        if len(titles) != len(set(titles)):
            raise ValueError("Choices must be unique")
        return values

    @field_validator("channel_points_per_vote")
    @classmethod
    def validate_channel_points_per_vote(cls, value: Optional[int], info):
        enabled = info.data.get("channel_points_voting_enabled")
        if enabled and not value:
            raise ValueError("channel_points_per_vote is required when channel points voting is enabled")
        if not enabled and value:
            raise ValueError("channel_points_per_vote must be empty when channel points voting is disabled")
        return value


class PollEnd(BaseModel):
    status: Literal["TERMINATED", "ARCHIVED"]


def _extract_user_id(user: Any) -> int:
    if not isinstance(user, dict):
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = user.get("id")
    if not isinstance(user_id, int) or user_id <= 0:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_id


async def get_twitch_credentials(user: dict) -> tuple[str, str, int]:
    """Resolve access token and broadcaster_id for current user."""
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


@router.post("/create", response_model=dict)
async def create_poll(poll: PollCreate, current_user: dict = Depends(get_current_user)):
    try:
        token, broadcaster_id, user_id = await get_twitch_credentials(current_user)
        data = {
            "broadcaster_id": broadcaster_id,
            "title": poll.title,
            "choices": [{"title": choice.title} for choice in poll.choices],
            "duration": poll.duration,
        }
        if poll.channel_points_voting_enabled:
            data["channel_points_voting_enabled"] = True
            data["channel_points_per_vote"] = poll.channel_points_per_vote

        logger.info("twitch_poll_creating", user_id=user_id, title=poll.title, choices_count=len(poll.choices), duration=poll.duration)
        response = await make_twitch_api_request("POST", "/polls", token, json_data=data)
        poll_data = response.get("data", [{}])[0]
        logger.info("twitch_poll_created", user_id=user_id, poll_id=poll_data.get("id"), title=poll.title)
        return {"success": True, "poll": poll_data}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("twitch_poll_create_error", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to create poll")


@router.patch("/{poll_id}/end", response_model=dict)
async def end_poll(poll_id: str, end_data: PollEnd, current_user: dict = Depends(get_current_user)):
    try:
        token, broadcaster_id, user_id = await get_twitch_credentials(current_user)
        data = {
            "broadcaster_id": broadcaster_id,
            "id": poll_id,
            "status": end_data.status,
        }

        logger.info("twitch_poll_ending", user_id=user_id, poll_id=poll_id, status=end_data.status)
        response = await make_twitch_api_request("PATCH", "/polls", token, json_data=data)
        poll_data = response.get("data", [{}])[0]
        logger.info("twitch_poll_ended", user_id=user_id, poll_id=poll_id, status=end_data.status)
        return {"success": True, "poll": poll_data}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("twitch_poll_end_error", poll_id=poll_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to end poll")


@router.get("/active", response_model=dict)
async def get_active_polls(current_user: dict = Depends(get_current_user)):
    try:
        token, broadcaster_id, user_id = await get_twitch_credentials(current_user)
        response = await make_twitch_api_request("GET", "/polls", token, params={"broadcaster_id": broadcaster_id})
        polls = response.get("data", [])
        logger.info("twitch_polls_fetched", user_id=user_id, count=len(polls))
        return {"success": True, "polls": polls}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("twitch_polls_fetch_error", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to load polls")


@router.get("/{poll_id}", response_model=dict)
async def get_poll(poll_id: str, current_user: dict = Depends(get_current_user)):
    try:
        token, broadcaster_id, _ = await get_twitch_credentials(current_user)
        response = await make_twitch_api_request(
            "GET",
            "/polls",
            token,
            params={"broadcaster_id": broadcaster_id, "id": poll_id},
        )
        polls = response.get("data", [])
        if not polls:
            raise HTTPException(status_code=404, detail="Poll not found")
        return {"success": True, "poll": polls[0]}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("twitch_poll_fetch_error", poll_id=poll_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to load poll")
