# repositories/blocked_user_repository.py
"""
Repository for TTS Blocked Users.
Follows Clean Architecture - abstracts all database access for TTSBlockedUser.
"""
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from repositories.base_repository import BaseRepository
from models.tts import TTSBlockedUser


class BlockedUserRepository(BaseRepository[TTSBlockedUser]):
    """Repository for TTSBlockedUser CRUD operations."""
    
    def __init__(self, db: Session):
        super().__init__(TTSBlockedUser, db)
    
    def get_by_user_id(self, user_id: int) -> List[TTSBlockedUser]:
        """Get all blocked users for a channel owner."""
        return self.db.query(TTSBlockedUser).filter(
            TTSBlockedUser.user_id == user_id
        ).all()
    
    def get_blocked_list(
        self,
        user_id: int,
    ) -> List[Dict[str, Any]]:
        """Get blocked users as list of dicts."""
        if not user_id:
            return []

        blocked = self.db.query(TTSBlockedUser).filter(
            TTSBlockedUser.user_id == user_id
        ).all()
        return [
            {
                "id": b.id,
                "username": b.username,
                "platform": b.platform,
                "channel_name": b.channel_name,
                "blocked_at": b.blocked_at.isoformat() if b.blocked_at else None,
                "reason": b.reason
            }
            for b in blocked
        ]
    
    def is_blocked(
        self,
        channel_name: str,
        platform: str,
        username: str,
        user_id: Optional[int] = None,
    ) -> bool:
        """Check if a user is blocked from TTS."""
        query = self.db.query(TTSBlockedUser).filter(
            TTSBlockedUser.channel_name == channel_name.lower(),
            TTSBlockedUser.platform == platform,
            TTSBlockedUser.username == username.lower()
        )
        
        if user_id is not None:
            query = query.filter(TTSBlockedUser.user_id == user_id)
        
        return query.first() is not None
    
    def block_user(
        self,
        channel_name: str,
        platform: str,
        username: str,
        user_id: int,
        blocked_by: Optional[int] = None,
        reason: Optional[str] = None
    ) -> Optional[TTSBlockedUser]:
        """Block a user from TTS. Returns None if already blocked."""
        if self.is_blocked(channel_name, platform, username, user_id):
            return None
        
        blocked = TTSBlockedUser(
            user_id=user_id,
            channel_name=channel_name.lower(),
            platform=platform,
            username=username.lower(),
            blocked_by=blocked_by,
            reason=reason
        )
        self.db.add(blocked)
        self.db.commit()
        self.db.refresh(blocked)
        return blocked
    
    def unblock_user(
        self,
        channel_name: str,
        platform: str,
        username: str,
        user_id: int,
    ) -> bool:
        """Unblock a user from TTS. Returns True if successful."""
        query = self.db.query(TTSBlockedUser).filter(
            TTSBlockedUser.channel_name == channel_name.lower(),
            TTSBlockedUser.platform == platform,
            TTSBlockedUser.username == username.lower()
        )
        
        query = query.filter(TTSBlockedUser.user_id == user_id)
        
        blocked = query.first()
        if not blocked:
            return False
        
        self.db.delete(blocked)
        self.db.commit()
        return True

    def remove_by_id(self, blocked_user_id: int, *, user_id: int) -> bool:
        """Delete a blocked-user row by id for the owner user."""
        blocked = (
            self.db.query(TTSBlockedUser)
            .filter(
                TTSBlockedUser.id == blocked_user_id,
                TTSBlockedUser.user_id == user_id,
            )
            .first()
        )
        if not blocked:
            return False

        self.db.delete(blocked)
        self.db.commit()
        return True
