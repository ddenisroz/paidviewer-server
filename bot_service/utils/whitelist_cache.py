"""Cached whitelist lookups used by TTS and custom voice access checks."""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from core.database import User, WhitelistedChannel
from utils.cache import TTL_WHITELIST, get_cached, invalidate_cache

logger = logging.getLogger(__name__)


def is_user_whitelisted_cached(user: User, db: Session) -> bool:
    """Return whether the user is present in the whitelist cache."""

    def _check_whitelist() -> bool:
        if user.twitch_username:
            twitch_username_lower = user.twitch_username.lower()
            twitch_whitelisted = (
                db.query(WhitelistedChannel)
                .filter(
                    WhitelistedChannel.channel_name == twitch_username_lower,
                    WhitelistedChannel.platform == "twitch",
                )
                .first()
            )
            if twitch_whitelisted:
                logger.debug("[OK] User %s whitelisted on Twitch: %s", user.id, twitch_username_lower)
                return True

        if user.vk_username:
            vk_username_lower = user.vk_username.lower()
            vk_whitelisted = (
                db.query(WhitelistedChannel)
                .filter(
                    WhitelistedChannel.channel_name == vk_username_lower,
                    WhitelistedChannel.platform == "vk",
                )
                .first()
            )
            if vk_whitelisted:
                logger.debug("[OK] User %s whitelisted on VK (username): %s", user.id, vk_username_lower)
                return True

        if user.vk_channel_name:
            vk_channel_lower = user.vk_channel_name.lower()
            vk_whitelisted = (
                db.query(WhitelistedChannel)
                .filter(
                    WhitelistedChannel.channel_name == vk_channel_lower,
                    WhitelistedChannel.platform == "vk",
                )
                .first()
            )
            if vk_whitelisted:
                logger.debug("[OK] User %s whitelisted on VK (channel_name): %s", user.id, vk_channel_lower)
                return True

        logger.debug(
            "[INFO] User %s not in whitelist (twitch=%s, vk=%s)",
            user.id,
            user.twitch_username,
            user.vk_username,
        )
        return False

    cache_key = f"whitelist:{user.id}:{user.twitch_username or ''}:{user.vk_username or ''}"
    return get_cached(cache_key, _check_whitelist, ttl=TTL_WHITELIST)


def is_channel_whitelisted_cached(channel_name: str, platform: str, db: Session) -> bool:
    """Return whether the channel is present in the whitelist cache."""

    def _check_channel() -> bool:
        whitelisted = (
            db.query(WhitelistedChannel)
            .filter(
                WhitelistedChannel.channel_name == channel_name.lower(),
                WhitelistedChannel.platform == platform,
            )
            .first()
        )
        return whitelisted is not None

    cache_key = f"whitelist_channel:{channel_name.lower()}:{platform}"
    return get_cached(cache_key, _check_channel, ttl=TTL_WHITELIST)


def invalidate_whitelist_cache(
    channel_name: Optional[str] = None,
    platform: Optional[str] = None,
    db: Optional[Session] = None,
) -> None:
    """Invalidate whitelist cache entries for a channel or the whole namespace."""

    if channel_name:
        channel_name_lower = channel_name.lower()
        invalidate_cache(f"whitelist_channel:{channel_name_lower}:{platform or ''}")

        if db:
            try:
                users_with_username = (
                    db.query(User)
                    .filter(
                        (User.twitch_username.ilike(channel_name_lower))
                        | (User.vk_username.ilike(channel_name_lower))
                        | (User.vk_channel_name.ilike(channel_name_lower))
                    )
                    .all()
                )

                for user in users_with_username:
                    cache_key = f"whitelist:{user.id}:{user.twitch_username or ''}:{user.vk_username or ''}"
                    invalidate_cache(cache_key)
                    logger.debug("Invalidated whitelist cache for user %s", user.id)
            except Exception as exc:
                logger.warning("Error invalidating user whitelist cache: %s", exc)
                invalidate_cache(f":{channel_name_lower}:")
                invalidate_cache(f":{channel_name_lower}")
        else:
            invalidate_cache(f":{channel_name_lower}:")
            invalidate_cache(f":{channel_name_lower}")
            invalidate_cache(channel_name_lower)
    else:
        invalidate_cache("whitelist")
