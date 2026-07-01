# bot_service/repositories/admin_user_repository.py
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import or_

from repositories.base_repository import BaseRepository
from models.user import AdminUser

class AdminUserRepository(BaseRepository[AdminUser]):
    """Repository for AdminUser entities."""
    
    def __init__(self, db: Session):
        super().__init__(AdminUser, db)
        
    def get_by_platform_user_id(self, platform_user_id: str) -> Optional[AdminUser]:
        """Get admin user by platform-specific user ID."""
        return self.db.query(AdminUser).filter(
            AdminUser.platform_user_id == str(platform_user_id)
        ).first()

    def delete_by_platform_user_ids(self, ids: List[str]) -> int:
        """Delete admin records matching list of platform IDs."""
        return self.db.query(AdminUser).filter(
            AdminUser.platform_user_id.in_(ids)
        ).delete(synchronize_session='fetch')
