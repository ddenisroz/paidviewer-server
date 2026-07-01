"""Pydantic models used by whitelist, YouTube, stream, and OBS endpoints."""

from datetime import datetime
import re
from typing import List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class WhitelistedChannelPublic(BaseModel):
    id: int
    channel_name: str
    platform: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AddToWhitelistRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9_.-]+$")
    platform: str = Field(default="twitch", pattern=r"^(twitch|vk)$")

    @model_validator(mode="before")
    @classmethod
    def normalize_payload(cls, data):
        if not isinstance(data, dict):
            return data

        payload = dict(data)
        if not payload.get("username") and payload.get("channel_name"):
            payload["username"] = payload.get("channel_name")

        raw_username = payload.get("username")
        if isinstance(raw_username, str):
            candidate = raw_username.strip()
            if candidate.startswith("http://") or candidate.startswith("https://"):
                parsed = urlparse(candidate)
                path_part = (parsed.path or "").rstrip("/").split("/")[-1]
                candidate = path_part or parsed.netloc or candidate
            if candidate.startswith("@"):
                candidate = candidate[1:]
            candidate = candidate.split("?", 1)[0].split("#", 1)[0]
            payload["username"] = candidate

        if not payload.get("platform"):
            payload["platform"] = "twitch"

        return payload

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_.-]+$", value):
            raise ValueError("Username can only contain letters, numbers, underscores, dots and dashes")
        return value.lower().strip()

    @field_validator("platform")
    @classmethod
    def validate_platform(cls, value: str) -> str:
        platform = (value or "").lower().strip()
        if platform not in {"twitch", "vk"}:
            raise ValueError("Platform must be 'twitch' or 'vk'")
        return platform


class WhitelistResponse(BaseModel):
    whitelist_users: List[WhitelistedChannelPublic]


class YouTubeVideoPublic(BaseModel):
    id: int
    video_id: str
    title: str
    url: str
    duration: int
    thumbnail_url: str
    added_at: datetime
    user_id: str
    requester_name: Optional[str] = None  # Requester display name
    channel_title: Optional[str] = None  # YouTube channel title

    model_config = ConfigDict(from_attributes=True)


class QueueResponse(BaseModel):
    current_video: Optional[YouTubeVideoPublic] = None
    queue: List[YouTubeVideoPublic] = []
    is_playing: bool = False


class BlockedBotPublic(BaseModel):
    id: int
    bot_name: str
    added_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AddBlockedBotRequest(BaseModel):
    bot_name: str


class UserPublic(BaseModel):
    id: int
    is_admin: bool
    is_blocked: bool = False
    blocked_reason: Optional[str] = None
    blocked_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UpdateTitleRequest(BaseModel):
    title: str


class UpdateCategoryRequest(BaseModel):
    categoryId: str


class StreamUpdateData(BaseModel):
    title: Optional[str] = None
    category_id: Optional[str] = None


class StreamUpdateRequest(BaseModel):
    twitch: Optional[StreamUpdateData] = None
    vk: Optional[StreamUpdateData] = None


class ObsUrlResponse(BaseModel):
    obs_token: str
