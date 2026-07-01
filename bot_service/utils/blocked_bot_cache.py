"""Cached blocked-bot lookups for runtime filtering."""

import logging
from typing import Set

from sqlalchemy.orm import Session

from core.database import BlockedBot
from utils.cache import get_cached, invalidate_cache

logger = logging.getLogger(__name__)

# Blocked bots rarely change, so a longer TTL is acceptable.
TTL_BLOCKED_BOTS = 600


def get_blocked_bots_set_cached(db: Session) -> Set[str]:
    """Return the lowercased set of blocked bot names with caching."""

    def _load_blocked_bots(db_session: Session):
        bots = db_session.query(BlockedBot.bot_name).all()
        return {bot.bot_name.lower() for bot in bots}

    cache_key = "blocked_bots:set"
    return get_cached(cache_key, _load_blocked_bots, db, ttl=TTL_BLOCKED_BOTS)


def is_bot_blocked_cached(bot_name: str, db: Session) -> bool:
    """Check whether a bot name is blocked, using the shared cache."""

    blocked_bots = get_blocked_bots_set_cached(db)
    return bot_name.lower() in blocked_bots


def invalidate_blocked_bots_cache():
    """Invalidate the blocked bots cache."""

    invalidate_cache("blocked_bots:set")
    logger.debug("Blocked bots cache invalidated")
