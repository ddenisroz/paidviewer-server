# bot_service/services/admin/whitelist_service.py
"""module: cleaned corrupted docstring."""

import logging
import re

from sqlalchemy.orm import Session

from models.pydantic_models import (
    WhitelistedChannelPublic,
    AddToWhitelistRequest,
    WhitelistResponse,
)
from repositories.whitelisted_channel_repository import WhitelistedChannelRepository
from utils.vk_channel_url import extract_vk_channel_slug
from utils.whitelist_cache import invalidate_whitelist_cache

logger = logging.getLogger(__name__)


class WhitelistService:
    """Service for whitelist channel management."""

    @staticmethod
    def _normalize_channel_name(raw_value: str, platform: str) -> str:
        value = (raw_value or "").strip().lower()
        if not value:
            return value

        value = value.replace("\\", "/").split("?", 1)[0].split("#", 1)[0]

        if platform == "vk":
            slug = extract_vk_channel_slug(value)
            if slug:
                return slug.lower()
            return value.lstrip("@").strip("/")

        # Twitch: support URL, @channel, plain channel.
        value = re.sub(r"^https?://(www\.)?twitch\.tv/", "", value)
        value = value.lstrip("@").strip("/")
        if "/" in value:
            value = value.split("/", 1)[0]
        return value

    async def get_whitelist(self, db: Session) -> WhitelistResponse:
        """Return all whitelisted channels."""
        repo = WhitelistedChannelRepository(db)
        channels = repo.get_all()
        return WhitelistResponse(
            whitelist_users=[
                WhitelistedChannelPublic.model_validate(ch) for ch in channels
            ]
        )

    async def add_to_whitelist(
        self, request: AddToWhitelistRequest, db: Session
    ) -> dict:
        """Add channel to whitelist."""
        repo = WhitelistedChannelRepository(db)
        platform = request.platform.lower()
        username = self._normalize_channel_name(request.username, platform)

        if not username:
            return {"error": "Channel name is empty after normalization"}

        existing = repo.get_by_name(username, platform)
        if existing:
            logger.warning(f"[WARN] WHITELIST: Channel '{username}' ({platform}) already exists")
            return {"error": f"User {username} is already in whitelist for {platform}"}

        repo.add_channel(username, platform)
        invalidate_whitelist_cache(channel_name=username, platform=platform, db=db)

        logger.info(f"[OK] WHITELIST: Channel '{username}' ({platform}) added")
        return {"message": f"User {username} added to whitelist for {platform}"}

    async def remove_from_whitelist(
        self, request: AddToWhitelistRequest, db: Session
    ) -> dict:
        """Remove channel from whitelist."""
        repo = WhitelistedChannelRepository(db)
        platform = request.platform.lower()
        username = self._normalize_channel_name(request.username, platform)

        if not username:
            return {"error": "Channel name is empty after normalization"}

        channel = repo.get_by_name(username, platform)
        if not channel:
            logger.warning(f"[WARN] WHITELIST: Channel '{username}' ({platform}) not found")
            return {"error": f"User {username} not found in whitelist for {platform}"}

        repo.remove_channel(channel)
        invalidate_whitelist_cache(channel_name=username, platform=platform, db=db)

        logger.info(f"[DELETE] WHITELIST: Channel '{username}' ({platform}) removed")
        return {"message": f"User {username} removed from whitelist for {platform}"}


# Singleton instance
whitelist_service = WhitelistService()
