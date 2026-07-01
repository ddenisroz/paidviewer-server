# bot_service/repositories/system_log_repository.py
"""
Repository for SystemLog entities.
Clean Architecture: abstracts DB access for system logging.
"""

import logging
from typing import List, Optional, Tuple, Dict, Any
from datetime import timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, func, case, distinct

from repositories.base_repository import BaseRepository
from core.database import SystemLog, User
from core.datetime_utils import utcnow_naive

logger = logging.getLogger(__name__)


class SystemLogRepository(BaseRepository[SystemLog]):
    """Repository for SystemLog entity."""
    
    def __init__(self, db: Session):
        super().__init__(SystemLog, db)
    
    def log_action(
        self,
        admin_id: int,
        action_type: str,
        description: str = None,
        target_user_id: int = None,
        target_resource: str = None,
        old_value: dict = None,
        new_value: dict = None,
        ip_address: str = None,
        user_agent: str = None,
        details: dict = None,
        status: str = "success",
        error_message: str = None
    ) -> Optional[SystemLog]:
        """Log an admin action."""
        try:
            log_entry = SystemLog(
                admin_id=admin_id,
                action_type=action_type,
                description=description,
                target_user_id=target_user_id,
                target_resource=target_resource,
                old_value=old_value,
                new_value=new_value,
                ip_address=ip_address,
                user_agent=user_agent,
                details=details,
                status=status,
                error_message=error_message,
                timestamp=utcnow_naive()
            )
            self.db.add(log_entry)
            self.db.commit()
            return log_entry
        except Exception as e:
            logger.error(f"Error logging action: {e}")
            self.db.rollback()
            return None
    
    def get_filtered_paginated(
        self,
        action_type: Optional[str] = None,
        admin_id: Optional[int] = None,
        target_user_id: Optional[int] = None,
        status: Optional[str] = None,
        days: int = 30,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[SystemLog], int]:
        """Get filtered logs with pagination."""
        filters = []
        
        # Time range filter
        cutoff_date = utcnow_naive() - timedelta(days=days)
        filters.append(SystemLog.timestamp >= cutoff_date)
        
        if action_type:
            filters.append(SystemLog.action_type == action_type)
        if admin_id:
            filters.append(SystemLog.admin_id == admin_id)
        if target_user_id:
            filters.append(SystemLog.target_user_id == target_user_id)
        if status:
            filters.append(SystemLog.status == status)
        
        query = self.db.query(SystemLog)
        if filters:
            query = query.filter(and_(*filters))
        
        total = query.count()
        logs = query.order_by(desc(SystemLog.timestamp)).limit(limit).offset(offset).all()
        
        return logs, total
    
    def get_users_by_ids(self, user_ids: List[int]) -> Dict[int, User]:
        """Batch fetch users by IDs."""
        if not user_ids:
            return {}
        users = self.db.query(User).filter(User.id.in_(user_ids)).all()
        return {u.id: u for u in users}
    
    def get_action_stats(self, days: int = 30) -> List[Tuple]:
        """Get action statistics by type."""
        cutoff_date = utcnow_naive() - timedelta(days=days)
        
        return self.db.query(
            SystemLog.action_type,
            func.count(SystemLog.id).label('count'),
            func.sum(case((SystemLog.status == 'success', 1), else_=0)).label('success_count'),
            func.sum(case((SystemLog.status == 'failed', 1), else_=0)).label('failed_count')
        ).filter(SystemLog.timestamp >= cutoff_date).group_by(SystemLog.action_type).all()
    
    def get_top_admins(self, days: int = 30, limit: int = 10) -> List[Tuple]:
        """Get top admins by action count."""
        cutoff_date = utcnow_naive() - timedelta(days=days)
        
        return self.db.query(
            SystemLog.admin_id,
            func.count(SystemLog.id).label('count')
        ).filter(
            SystemLog.timestamp >= cutoff_date
        ).group_by(
            SystemLog.admin_id
        ).order_by(
            desc(func.count(SystemLog.id))
        ).limit(limit).all()
    
    def get_total_count(self, days: int = 30) -> int:
        """Get total log count for time period."""
        cutoff_date = utcnow_naive() - timedelta(days=days)
        return self.db.query(SystemLog).filter(SystemLog.timestamp >= cutoff_date).count()
    
    def get_distinct_action_types(self) -> List[str]:
        """Get all unique action types."""
        results = self.db.query(distinct(SystemLog.action_type)).all()
        return [action[0] for action in results if action[0]]
