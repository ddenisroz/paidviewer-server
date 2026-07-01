# bot_service/repositories/database_stats_repository.py
"""
Repository for database statistics and maintenance queries.
"""

import logging
from typing import Dict, Any
from datetime import datetime, timedelta

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from core.database import ChatMessage, User, PsychologyAnalysis

logger = logging.getLogger(__name__)


class DatabaseStatsRepository:
    """
    Repository for database statistics queries.
    Encapsulates all direct DB queries for stats collection.
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    # ========== Chat Messages ==========
    
    def count_total_messages(self) -> int:
        """Count total chat messages."""
        return self.db.query(ChatMessage).count()
    
    def count_messages_by_platform(self, platform: str) -> int:
        """Count messages by platform (twitch, vk, etc.)."""
        return self.db.query(ChatMessage).filter(
            ChatMessage.platform == platform
        ).count()
    
    def count_old_messages(self, retention_days: int) -> int:
        """Count messages older than retention period."""
        from core.datetime_utils import utcnow_naive
        cutoff = utcnow_naive() - timedelta(days=retention_days)
        return self.db.query(ChatMessage).filter(
            ChatMessage.timestamp < cutoff
        ).count()
    
    def count_users_over_message_limit(self, limit: int) -> int:
        """Count users who exceed the message limit."""
        return self.db.query(
            ChatMessage.user_id,
            func.count(ChatMessage.id).label('message_count')
        ).group_by(ChatMessage.user_id).having(
            func.count(ChatMessage.id) > limit
        ).count()
    
    def delete_old_messages(self, retention_days: int) -> int:
        """Delete messages older than retention period. Returns count."""
        from core.datetime_utils import utcnow_naive
        cutoff = utcnow_naive() - timedelta(days=retention_days)
        
        count = self.db.query(ChatMessage).filter(
            ChatMessage.timestamp < cutoff
        ).delete()
        self.db.commit()
        return count
    
    def get_oldest_messages_ids(self, limit: int) -> list:
        """Get IDs of oldest messages."""
        results = self.db.query(ChatMessage.id).order_by(
            ChatMessage.timestamp.asc()
        ).limit(limit).all()
        return [r[0] for r in results]
    
    def delete_messages_by_ids(self, message_ids: list) -> int:
        """Delete messages by IDs. Returns count."""
        if not message_ids:
            return 0
        count = self.db.query(ChatMessage).filter(
            ChatMessage.id.in_(message_ids)
        ).delete(synchronize_session=False)
        self.db.commit()
        return count
    
    def get_user_message_counts_over_limit(self, limit: int) -> list:
        """Get (user_id, count) for users over limit."""
        return self.db.query(
            ChatMessage.user_id,
            func.count(ChatMessage.id).label('message_count')
        ).group_by(ChatMessage.user_id).having(
            func.count(ChatMessage.id) > limit
        ).all()
    
    def get_oldest_messages_for_user(self, user_id: int, count: int) -> list:
        """Get oldest messages for a specific user."""
        return self.db.query(ChatMessage).filter(
            ChatMessage.user_id == user_id
        ).order_by(ChatMessage.timestamp.asc()).limit(count).all()
    
    # ========== Users ==========
    
    def count_total_users(self) -> int:
        """Count total users."""
        return self.db.query(User).count()
    
    # ========== Psychology (legacy) ==========
    
    def count_total_analyses(self) -> int:
        """Count total psychology analyses."""
        return self.db.query(PsychologyAnalysis).count()
    
    # ========== Database Size ==========
    
    def get_database_size_bytes(self) -> int:
        """Get actual database size in bytes (PostgreSQL)."""
        try:
            result = self.db.execute(text("SELECT pg_database_size(current_database())"))
            size = result.scalar()
            return size if size else 0
        except Exception as e:
            logger.error(f"Error getting database size: {e}")
            return 0
