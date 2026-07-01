# bot_service/repositories/drops_reward_repository.py
"""
Repository for DropsReward entities.
Clean Architecture: abstracts DB access for drops rewards.
"""

import logging
from typing import List, Optional, Dict, Any
from sqlalchemy import func
from sqlalchemy.orm import Session

from repositories.base_repository import BaseRepository
from core.database import DropsReward, DropsQuality, DropsConfig
from core.datetime_utils import utcnow_naive

logger = logging.getLogger(__name__)


class DropsRewardRepository(BaseRepository[DropsReward]):
    """Repository for DropsReward entity."""
    
    def __init__(self, db: Session):
        super().__init__(DropsReward, db)
    
    def get_config_by_token(self, token: str) -> Optional[DropsConfig]:
        """Get DropsConfig by widget token."""
        return self.db.query(DropsConfig).filter(DropsConfig.widget_token == token).first()
    
    def get_quality_by_id(self, quality_id: int) -> Optional[DropsQuality]:
        """Get DropsQuality by ID."""
        return self.db.query(DropsQuality).filter(DropsQuality.id == quality_id).first()
    
    def get_quality_by_name(self, name: str) -> Optional[DropsQuality]:
        """Get DropsQuality by name."""
        normalized_name = (name or "").strip().lower()
        return self.db.query(DropsQuality).filter(func.lower(DropsQuality.name) == normalized_name).first()
    
    def get_all_qualities(self) -> List[DropsQuality]:
        """Get all DropsQuality records."""
        return self.db.query(DropsQuality).all()
    
    def get_qualities_by_ids(self, quality_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        """Get DropsQuality records by IDs, returns dict mapping id->quality."""
        if not quality_ids:
            return {}
        qualities = self.db.query(DropsQuality).filter(DropsQuality.id.in_(quality_ids)).all()
        return {q.id: {"name": q.name, "color": q.color, "id": q.id} for q in qualities}
    
    def get_by_user_and_channel(
        self,
        user_id: int,
        channel_name: str,
        quality_id: Optional[int] = None
    ) -> List[DropsReward]:
        """Get rewards for a user's channel, optionally filtered by quality."""
        query = self.db.query(DropsReward).filter(
            DropsReward.user_id == user_id,
            DropsReward.channel_name == channel_name
        )
        if quality_id:
            query = query.filter(DropsReward.quality_id == quality_id)
        return query.all()

    def get_active_by_user_and_channel(
        self,
        user_id: int,
        channel_name: str,
        quality_id: Optional[int] = None,
    ) -> List[DropsReward]:
        """Get active rewards for an authenticated user's channel."""
        query = self.db.query(DropsReward).filter(
            DropsReward.user_id == user_id,
            DropsReward.channel_name == channel_name,
            DropsReward.is_active.is_(True),
        )
        if quality_id:
            query = query.filter(DropsReward.quality_id == quality_id)
        return query.all()

    def get_by_filters(
        self,
        channel_name: str,
        user_id: Optional[int] = None,
        session_id: Optional[str] = None,
        quality_id: Optional[int] = None,
        is_active: bool = True
    ) -> List[DropsReward]:
        """Get rewards by generic filters."""
        query = self.db.query(DropsReward).filter(
            DropsReward.channel_name == channel_name
        )
        
        if is_active:
            query = query.filter(DropsReward.is_active.is_(True))
            
        if user_id:
            query = query.filter(DropsReward.user_id == user_id)
        elif session_id:
            query = query.filter(DropsReward.session_id == session_id)
            
        if quality_id:
            query = query.filter(DropsReward.quality_id == quality_id)
            
        return query.all()
    
    def get_by_id_and_user(self, reward_id: int, user_id: int) -> Optional[DropsReward]:
        """Get reward by ID owned by specific user."""
        return self.db.query(DropsReward).filter(
            DropsReward.id == reward_id,
            DropsReward.user_id == user_id
        ).first()
    
    def create(
        self,
        user_id: int,
        channel_name: str,
        platform: str,
        name: str,
        quality_id: int,
        reward_type: str,
        description: Optional[str] = None,
        weight: int = 100,
        reward_value: str = "",
        image_url: Optional[str] = None,
        sound_volume: float = 1.0,
        is_active: bool = True
    ) -> DropsReward:
        """Create a new drops reward."""
        reward = DropsReward(
            user_id=user_id,
            channel_name=channel_name,
            platform=platform,
            name=name,
            description=description,
            quality_id=quality_id,
            weight=weight,
            reward_type=reward_type,
            reward_value=reward_value,
            image_url=image_url,
            sound_volume=sound_volume,
            is_active=is_active
        )
        self.db.add(reward)
        self.db.commit()
        self.db.refresh(reward)
        return reward
    
    def update(self, reward: DropsReward, update_data: Dict[str, Any]) -> DropsReward:
        """Update a reward with given data."""
        for field, value in update_data.items():
            if hasattr(reward, field):
                setattr(reward, field, value)
        reward.updated_at = utcnow_naive()
        self.db.commit()
        self.db.refresh(reward)
        return reward
    
    def delete(self, reward: DropsReward) -> str:
        """Delete a reward. Returns the channel name for cache invalidation."""
        channel_name = reward.channel_name
        self.db.delete(reward)
        self.db.commit()
        return channel_name
    
    def update_image(self, reward: DropsReward, image_url: str) -> DropsReward:
        """Update reward's image URL."""
        reward.image_url = image_url
        reward.updated_at = utcnow_naive()
        self.db.commit()
        return reward
    
    def update_sound(self, reward: DropsReward, sound_file: str) -> DropsReward:
        """Update reward's sound file."""
        reward.sound_file = sound_file
        reward.updated_at = utcnow_naive()
        self.db.commit()
        return reward
