# bot_service/repositories/user_session_repository.py
from typing import Optional, List
from sqlalchemy.orm import Session
from datetime import datetime

from repositories.base_repository import BaseRepository
from models.user import UserSession

class UserSessionRepository(BaseRepository[UserSession]):
    """Repository for UserSession entities."""
    
    def __init__(self, db: Session):
        super().__init__(UserSession, db)
        
    def get_by_session_id(self, session_id: str) -> Optional[UserSession]:
        """Get session by ID."""
        return self.db.query(UserSession).filter(
            UserSession.session_id == session_id
        ).first()

    def delete_by_user_id(self, user_id: int) -> int:
        """Delete all sessions for a user."""
        return self.db.query(UserSession).filter(
            UserSession.user_id == user_id
        ).delete()
    
    def get_active_by_user(self, user_id: int) -> List[UserSession]:
        """Get all active sessions for a user."""
        return self.db.query(UserSession).filter(
            UserSession.user_id == user_id,
            UserSession.is_active == True
        ).all()
