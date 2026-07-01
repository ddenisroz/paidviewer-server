# bot_service/services/admin/blocked_bots_service.py
"""
Service for managing blocked bot accounts.
"""

import logging
from typing import List

from sqlalchemy.orm import Session

from models.pydantic_models import BlockedBotPublic, AddBlockedBotRequest


from repositories.blocked_bot_repository import BlockedBotRepository

logger = logging.getLogger(__name__)


class BlockedBotsService:
    """Service for managing the blocked-bots list."""

    async def get_blocked_bots(self, db: Session) -> List[BlockedBotPublic]:
        """Get the list of blocked bots."""
        repo = BlockedBotRepository(db)
        bots = repo.get_all()
        return [BlockedBotPublic.model_validate(bot) for bot in bots]

    async def add_blocked_bot(
        self, request: AddBlockedBotRequest, db: Session
    ) -> dict:
        """Add a bot to the blocked list."""
        repo = BlockedBotRepository(db)
        bot_name = request.bot_name.lower()

        existing = repo.get_by_name(bot_name)

        if existing:
            return {"message": f"Bot {bot_name} is already blocked"}

        repo.add_bot(bot_name)

        logger.info(f"[OK] Bot {bot_name} added to blocked list")
        return {"message": f"Bot {bot_name} added to blocked list"}

    async def remove_blocked_bot(self, bot_name: str, db: Session) -> dict:
        """Remove a bot from the blocked list."""
        repo = BlockedBotRepository(db)
        bot_name = bot_name.lower()

        bot = repo.get_by_name(bot_name)

        if not bot:
            return {"message": f"Bot {bot_name} not found in blocked list"}

        repo.remove_bot(bot)

        logger.info(f"[DELETE] Bot {bot_name} removed from blocked list")
        return {"message": f"Bot {bot_name} removed from blocked list"}


# Singleton instance
blocked_bots_service = BlockedBotsService()
