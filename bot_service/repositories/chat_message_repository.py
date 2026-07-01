# bot_service/repositories/chat_message_repository.py
"""
Repository for working with chat messages.
"""

import logging
from typing import Optional, List
from datetime import datetime

from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from core.database import ChatMessage
from repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class ChatMessageRepository(BaseRepository[ChatMessage]):
    """
    Repository for ChatMessage.
    
    Usage:
        repo = ChatMessageRepository(db)
        messages = repo.get_by_channel(user_id, "channel_name", limit=50)
    """
    
    def __init__(self, db: Session):
        super().__init__(ChatMessage, db)
    
    def get_by_channel(
        self,
        user_id: int,
        channel_name: str,
        platform: Optional[str] = None,
        limit: int = 50,
        include_deleted: bool = False,
    ) -> List[ChatMessage]:
        """Get channel messages."""
        query = self.db.query(ChatMessage).filter(
            ChatMessage.user_id == user_id,
            func.lower(ChatMessage.channel_name) == channel_name.lower(),
        )
        
        if not include_deleted:
            query = query.filter(ChatMessage.is_deleted.is_(False))
        
        if platform:
            query = query.filter(ChatMessage.platform == platform)
        
        return query.order_by(ChatMessage.timestamp.desc()).limit(limit).all()
    
    def get_recent(self, user_id: int, limit: int = 100) -> List[ChatMessage]:
        """Get the latest messages for a user."""
        return self.db.query(ChatMessage).filter(
            ChatMessage.user_id == user_id,
            ChatMessage.is_deleted.is_(False),
        ).order_by(ChatMessage.timestamp.desc()).limit(limit).all()

    def get_history_by_platforms(
        self, user_id: int, platforms: List[str], limit: int = 50
    ) -> List[ChatMessage]:
        """Get message history for the selected platforms."""
        return self.db.query(ChatMessage).filter(
            ChatMessage.user_id == user_id,
            ChatMessage.platform.in_(platforms)
        ).order_by(ChatMessage.timestamp.desc()).limit(limit).all()

    def get_recent_by_author(
        self,
        user_id: int,
        author_username: str,
        platform: Optional[str] = None,
        limit: int = 200
    ) -> List[ChatMessage]:
        """Get recent messages by author across all channels."""
        if not author_username:
            return []
        query = self.db.query(ChatMessage).filter(
            ChatMessage.user_id == user_id,
            ChatMessage.is_deleted.is_(False),
            func.lower(ChatMessage.author_username) == author_username.lower(),
        )
        if platform:
            query = query.filter(ChatMessage.platform == platform)
        return query.order_by(ChatMessage.timestamp.desc()).limit(limit).all()

    def get_recent_by_author_in_channel(
        self,
        user_id: int,
        author_username: str,
        channel_name: str,
        platform: Optional[str] = None,
        limit: int = 80
    ) -> List[ChatMessage]:
        """Get recent messages by author in a specific channel."""
        if not author_username or not channel_name:
            return []
        query = self.db.query(ChatMessage).filter(
            ChatMessage.user_id == user_id,
            ChatMessage.is_deleted.is_(False),
            func.lower(ChatMessage.author_username) == author_username.lower(),
            func.lower(ChatMessage.channel_name) == channel_name.lower(),
        )
        if platform:
            query = query.filter(ChatMessage.platform == platform)
        return query.order_by(ChatMessage.timestamp.desc()).limit(limit).all()

    def author_exists_in_channel(
        self,
        user_id: int,
        author_username: str,
        channel_name: str,
        platform: Optional[str] = None,
    ) -> bool:
        """Return True when the author already exists in stored chat history for the channel."""
        if not author_username or not channel_name:
            return False

        query = self.db.query(ChatMessage.id).filter(
            ChatMessage.user_id == user_id,
            ChatMessage.is_deleted.is_(False),
            func.lower(ChatMessage.author_username) == author_username.lower(),
            func.lower(ChatMessage.channel_name) == channel_name.lower(),
        )
        if platform:
            query = query.filter(ChatMessage.platform == platform)

        return query.first() is not None
    
    def create(
        self,
        user_id: int,
        channel_name: str,
        platform: str,
        message: str,
        author_username: Optional[str] = None,
        author_id: Optional[str] = None,
        role: Optional[str] = None,
        badges: Optional[str] = None,
    ) -> ChatMessage:
        """Create a new message."""
        chat_msg = ChatMessage(
            user_id=user_id,
            channel_name=channel_name,
            platform=platform,
            message=message,
            author_username=author_username,
            author_id=author_id,
            role=role,
            badges=badges,
            timestamp=datetime.utcnow(),
            is_deleted=False,
        )
        self.db.add(chat_msg)
        self.db.commit()
        self.db.refresh(chat_msg)
        return chat_msg
    
    def soft_delete(self, message_id: int) -> bool:
        """Soft-delete a message."""
        msg = self.db.query(ChatMessage).filter(ChatMessage.id == message_id).first()
        if msg:
            msg.is_deleted = True
            self.db.commit()
            return True
        return False
    
    def delete_by_user(self, user_id: int) -> int:
        """Delete all messages for a user."""
        result = self.db.query(ChatMessage).filter(ChatMessage.user_id == user_id).delete()
        self.db.commit()
        return result
    
    def get_count_by_channel(self, user_id: int, channel_name: str) -> int:
        """Get the number of messages in a channel."""
        return self.db.query(ChatMessage).filter(
            ChatMessage.user_id == user_id,
            func.lower(ChatMessage.channel_name) == channel_name.lower(),
            ChatMessage.is_deleted.is_(False),
        ).count()
    
    def get_paginated(
        self,
        user_id: int,
        channel_name: Optional[str] = None,
        platform: Optional[str] = None,
        page: int = 1,
        limit: int = 100
    ) -> tuple:
        """Get paginated chat messages."""
        query = self.db.query(ChatMessage).filter(ChatMessage.user_id == user_id)
        if channel_name:
            query = query.filter(ChatMessage.channel_name == channel_name)
        if platform:
            query = query.filter(ChatMessage.platform == platform)
        
        total = query.count()
        offset = (page - 1) * limit
        messages = query.order_by(ChatMessage.timestamp.desc()).offset(offset).limit(limit).all()
        return messages, total
    
    def get_stats(self, user_id: int, channel_name: Optional[str] = None, platform: Optional[str] = None) -> dict:
        """Get statistics for chat messages."""
        from datetime import timedelta
        from core.datetime_utils import utcnow_naive
        
        query = self.db.query(ChatMessage).filter(ChatMessage.user_id == user_id)
        if channel_name:
            query = query.filter(ChatMessage.channel_name == channel_name)
        if platform:
            query = query.filter(ChatMessage.platform == platform)
        
        yesterday = utcnow_naive() - timedelta(hours=24)
        messages_24h = query.filter(ChatMessage.timestamp >= yesterday).count()
        total_messages = query.count()
        unique_viewers = query.distinct(ChatMessage.viewer_name).count()
        
        return {
            "total_messages": total_messages,
            "messages_24h": messages_24h,
            "unique_viewers": unique_viewers
        }

    def get_messages_for_analysis(
        self, user_id: int, platform: str, since: datetime, limit: int = 100
    ) -> List[ChatMessage]:
        """Get messages for psychology analysis."""
        return self.db.query(ChatMessage).filter(
            ChatMessage.user_id == user_id,
            ChatMessage.platform == platform,
            ChatMessage.timestamp >= since,
            ChatMessage.is_deleted.is_(False)
        ).order_by(desc(ChatMessage.timestamp)).limit(limit).all()

    # === Cleanup Methods ===

    def delete_old_by_user_platform(
        self, user_id: int, platform: str, cutoff_date: datetime
    ) -> int:
        """Delete old messages for user/platform before cutoff date."""
        count = self.db.query(ChatMessage).filter(
            ChatMessage.user_id == user_id,
            ChatMessage.platform == platform,
            ChatMessage.timestamp < cutoff_date
        ).delete(synchronize_session=False)
        return count

    def count_by_user_channel_platform(
        self, user_id: int, channel_name: str, platform: str
    ) -> int:
        """Count messages for user/channel/platform."""
        return self.db.query(ChatMessage).filter(
            ChatMessage.user_id == user_id,
            ChatMessage.channel_name == channel_name,
            ChatMessage.platform == platform
        ).count()

    def count_by_user_platform(self, user_id: int, platform: str) -> int:
        """Count messages for user/platform."""
        return self.db.query(ChatMessage).filter(
            ChatMessage.user_id == user_id,
            ChatMessage.platform == platform
        ).count()
