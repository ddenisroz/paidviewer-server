# bot_service/services/chat_history_service.py
"""
Chat history service for retrieving and formatting messages.
"""

import json
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

from sqlalchemy.orm import Session
from core.database import ChatMessage


from repositories.chat_message_repository import ChatMessageRepository
from repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


@dataclass
class ChatMessageDTO:
    """DTO for a chat message."""
    id: int
    author: str
    author_name: str
    content: str
    message: str
    platform: str
    timestamp: Optional[str]
    channel: str
    role: Optional[str]
    badges: Optional[List[Dict[str, Any]]]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ChatHistoryService:
    """
    Service for working with chat history.
    """
    
    def get_chat_history(
        self,
        user_id: int,
        channel: Optional[str],
        platform: Optional[str],
        limit: int,
        db: Session,
    ) -> List[ChatMessageDTO]:
        """
        Return chat message history.
        """
        # If channel is not provided, use the user's default channel.
        if not channel:
            channel, platform = self._get_user_channel(user_id, db)
            if not channel:
                logger.warning(f"[CHAT] User {user_id} has no channels")
                return []
        
        logger.info(
            f"[CHAT] Querying messages: user_id={user_id}, "
            f"channel={channel}, platform={platform}, limit={limit}"
        )
        
        repo = ChatMessageRepository(db)
        messages = repo.get_by_channel(
            user_id=user_id,
            channel_name=channel,
            platform=platform,
            limit=limit,
            include_deleted=False
        )
        
        logger.info(f"[CHAT] Found {len(messages)} messages in database")
        
        # Convert to DTOs and reverse for chronological order.
        result = []
        for msg in reversed(messages):
            dto = self._message_to_dto(msg)
            result.append(dto)
        
        return result
    
    def _get_user_channel(
        self, 
        user_id: int, 
        db: Session
    ) -> tuple[Optional[str], Optional[str]]:
        """Return the user's default channel."""
        user_repo = UserRepository(db)
        db_user = user_repo.get(user_id)
        if not db_user:
            return None, None
        
        if db_user.twitch_username:
            return db_user.twitch_username, "twitch"
        elif db_user.vk_channel_name or db_user.vk_username:
            return db_user.vk_channel_name or db_user.vk_username, "vk"
        
        return None, None
    
    def _message_to_dto(self, msg: ChatMessage) -> ChatMessageDTO:
        """Convert a message model to DTO."""
        # Parse badges when they are stored as a JSON string.
        badges_list = getattr(msg, 'badges', None)
        if isinstance(badges_list, str):
            try:
                badges_list = json.loads(badges_list)
            except Exception:
                badges_list = None
        
        author = getattr(msg, 'author_username', None) or 'unknown'
        timestamp = msg.timestamp.isoformat() if msg.timestamp else None
        
        return ChatMessageDTO(
            id=msg.id,
            author=author,
            author_name=author,
            content=msg.message,
            message=msg.message,
            platform=msg.platform,
            timestamp=timestamp,
            channel=msg.channel_name,
            role=getattr(msg, 'role', None),
            badges=badges_list,
        )


# Singleton instance
chat_history_service = ChatHistoryService()
