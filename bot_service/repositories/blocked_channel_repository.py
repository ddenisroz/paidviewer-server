# bot_service/repositories/blocked_channel_repository.py
"""
Repository for BlockedChannel entities.
Clean Architecture: abstracts DB access for channel blocking.
"""

import logging
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session

from repositories.base_repository import BaseRepository
from core.database import BlockedChannel

logger = logging.getLogger(__name__)


class BlockedChannelRepository(BaseRepository[BlockedChannel]):
    """Repository for BlockedChannel entity."""
    
    def __init__(self, db: Session):
        super().__init__(BlockedChannel, db)
    
    def get_active_paginated(
        self,
        search: Optional[str] = None,
        page: int = 1,
        limit: int = 50
    ) -> Tuple[List[BlockedChannel], int]:
        """Get active blocked channels with pagination.
        
        Returns:
            Tuple of (channels list, total count)
        """
        query = self.db.query(BlockedChannel).filter(BlockedChannel.is_active == True)
        
        if search:
            query = query.filter(BlockedChannel.channel_name.ilike(f"%{search}%"))
        
        total = query.count()
        offset = (page - 1) * limit
        channels = query.order_by(BlockedChannel.created_at.desc()).offset(offset).limit(limit).all()
        
        return channels, total
    
    def is_blocked(self, channel_name: str) -> bool:
        """Check if a channel is currently blocked."""
        return self.db.query(BlockedChannel).filter(
            BlockedChannel.channel_name == channel_name.lower(),
            BlockedChannel.is_active == True
        ).first() is not None
    
    def block(
        self,
        channel_name: str,
        reason: Optional[str] = None,
        blocked_by: Optional[str] = None
    ) -> BlockedChannel:
        """Block a channel."""
        channel = BlockedChannel(
            channel_name=channel_name.lower().strip(),
            reason=reason,
            blocked_by=blocked_by,
            is_active=True
        )
        self.db.add(channel)
        self.db.commit()
        self.db.refresh(channel)
        return channel
    
    def update_reason(self, channel_id: int, reason: str) -> Optional[BlockedChannel]:
        """Update the reason for a blocked channel."""
        channel = self.get_by_id(channel_id)
        if not channel:
            return None
        
        channel.reason = reason
        self.db.commit()
        return channel
    
    def unblock(self, channel_id: int) -> Optional[BlockedChannel]:
        """Unblock a channel (soft delete)."""
        channel = self.get_by_id(channel_id)
        if not channel:
            return None
        
        channel.is_active = False
        self.db.commit()
        return channel
