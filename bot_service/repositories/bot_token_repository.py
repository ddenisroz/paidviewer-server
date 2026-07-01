# bot_service/repositories/bot_token_repository.py
from typing import Optional
from sqlalchemy.orm import Session

from repositories.base_repository import BaseRepository
from models.bot_token import BotToken


class BotTokenRepository(BaseRepository[BotToken]):
    """
    Repository for BotToken entity.
    Handles storage of bot OAuth tokens.
    """
    def __init__(self, db: Session):
        super().__init__(BotToken, db)

    def get_by_platform(self, platform: str) -> Optional[BotToken]:
        """Get bot token by platform."""
        return self.db.query(BotToken).filter(BotToken.platform == platform).first()

    def save(self, token: BotToken) -> BotToken:
        """Save (add or update) bot token."""
        if not token.id:
            self.db.add(token)
        self.db.commit()
        self.db.refresh(token)
        return token
