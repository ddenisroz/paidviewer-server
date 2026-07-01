# bot_service/repositories/donation_alert_repository.py
"""
Repository for DonationAlert entity.
Clean Architecture: abstracts DB access for donation alerts.
"""

import logging
from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func

from repositories.base_repository import BaseRepository
from core.database import DonationAlert

logger = logging.getLogger(__name__)


class DonationAlertRepository(BaseRepository[DonationAlert]):
    """Repository for DonationAlert entity."""
    
    def __init__(self, db: Session):
        super().__init__(DonationAlert, db)
    
    def get_by_user_id(
        self, 
        user_id: int, 
        limit: int = 50, 
        offset: int = 0
    ) -> List[DonationAlert]:
        """Get donations for user with pagination."""
        return self.db.query(DonationAlert).filter(
            DonationAlert.user_id == user_id
        ).order_by(DonationAlert.processed_at.desc()).offset(offset).limit(limit).all()
    
    def count_by_user_id(self, user_id: int) -> int:
        """Count total donations for user."""
        return self.db.query(DonationAlert).filter(
            DonationAlert.user_id == user_id
        ).count()
    
    def count_by_user_since(self, user_id: int, since: datetime) -> int:
        """Count donations for user since a specific date."""
        return self.db.query(DonationAlert).filter(
            DonationAlert.user_id == user_id,
            DonationAlert.processed_at > since
        ).count()
    
    def sum_amount_by_user(self, user_id: int) -> float:
        """Get total amount of donations for user."""
        result = self.db.query(func.sum(DonationAlert.amount)).filter(
            DonationAlert.user_id == user_id
        ).scalar()
        return result or 0.0
    
    def sum_amount_by_user_since(self, user_id: int, since: datetime) -> float:
        """Get total amount of donations for user since a specific date."""
        result = self.db.query(func.sum(DonationAlert.amount)).filter(
            DonationAlert.user_id == user_id,
            DonationAlert.processed_at > since
        ).scalar()
        return result or 0.0
