# bot_service/repositories/blocked_bot_repository.py
from typing import Optional, List
from sqlalchemy.orm import Session
from core.database import BlockedBot
from repositories.base_repository import BaseRepository

class BlockedBotRepository(BaseRepository[BlockedBot]):
    def __init__(self, db: Session):
        super().__init__(BlockedBot, db)

    def get_all(self) -> List[BlockedBot]:
        return self.db.query(BlockedBot).all()

    def get_by_name(self, bot_name: str) -> Optional[BlockedBot]:
        return self.db.query(BlockedBot).filter(
            BlockedBot.bot_name == bot_name
        ).first()

    def add_bot(self, bot_name: str) -> BlockedBot:
        bot = BlockedBot(bot_name=bot_name)
        self.db.add(bot)
        self.db.commit()
        self.db.refresh(bot)
        return bot

    def remove_bot(self, bot: BlockedBot):
        self.db.delete(bot)
        self.db.commit()
