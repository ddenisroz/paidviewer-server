# bot_service/repositories/whitelisted_channel_repository.py
from typing import Optional, List
from sqlalchemy.orm import Session
from core.database import WhitelistedChannel
from repositories.base_repository import BaseRepository

class WhitelistedChannelRepository(BaseRepository[WhitelistedChannel]):
    def __init__(self, db: Session):
        super().__init__(WhitelistedChannel, db)

    def get_all(self) -> List[WhitelistedChannel]:
        return self.db.query(WhitelistedChannel).order_by(WhitelistedChannel.created_at.desc()).all()

    def get_by_name(self, channel_name: str, platform: Optional[str] = None) -> Optional[WhitelistedChannel]:
        query = self.db.query(WhitelistedChannel).filter(
            WhitelistedChannel.channel_name == channel_name.lower()
        )
        if platform:
            query = query.filter(WhitelistedChannel.platform == platform.lower())
        return query.first()

    def add_channel(self, channel_name: str, platform: str = 'twitch') -> WhitelistedChannel:
        channel = WhitelistedChannel(
            channel_name=channel_name.lower(),
            platform=platform.lower(),
        )
        self.db.add(channel)
        self.db.commit()
        self.db.refresh(channel)
        return channel

    def remove_channel(self, channel: WhitelistedChannel):
        self.db.delete(channel)
        self.db.commit()

    def delete_by_channel_name(self, channel_name: str, platform: Optional[str] = None) -> int:
        """Delete channel by name."""
        query = self.db.query(WhitelistedChannel).filter(
            WhitelistedChannel.channel_name == channel_name.lower()
        )
        if platform:
            query = query.filter(WhitelistedChannel.platform == platform.lower())
        result = query.delete()
        self.db.commit()
        return result
