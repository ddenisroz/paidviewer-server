from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, func

from repositories.base_repository import BaseRepository
from models.points import ChannelPoints, ChannelReward, RewardQueue, PointsTransaction

class PointsRepository(BaseRepository[ChannelPoints]):
    """
    Repository for Points system entities.
    Handles ChannelPoints, ChannelReward, and RewardQueue.
    """
    def __init__(self, db: Session):
        super().__init__(ChannelPoints, db)

    # === ChannelPoints ===

    def get_user_points(self, user_id: int, viewer_id: str, platform: str, channel_name: str) -> Optional[ChannelPoints]:
        return self.db.query(ChannelPoints).filter(
            and_(
                ChannelPoints.user_id == user_id,
                ChannelPoints.viewer_id == viewer_id,
                ChannelPoints.platform == platform,
                ChannelPoints.channel_name == channel_name
            )
        ).first()
    
    def get_user_points_for_update(self, user_id: int, viewer_id: str, platform: str, channel_name: str) -> Optional[ChannelPoints]:
        return self.db.query(ChannelPoints).filter(
            and_(
                ChannelPoints.user_id == user_id,
                ChannelPoints.viewer_id == viewer_id,
                ChannelPoints.platform == platform,
                ChannelPoints.channel_name == channel_name
            )
        ).with_for_update().first()

    def get_leaderboard(self, user_id: int, channel_name: str, platform: str = None, limit: int = 10) -> List[ChannelPoints]:
        query = self.db.query(ChannelPoints).filter(
            and_(
                ChannelPoints.user_id == user_id,
                ChannelPoints.channel_name == channel_name
            )
        )
        if platform:
            query = query.filter(ChannelPoints.platform == platform)
        
        return query.order_by(desc(ChannelPoints.points)).limit(limit).all()
    
    def get_channel_stats(self, user_id: int, channel_name: str) -> dict:
        total_users = self.db.query(func.count(ChannelPoints.id)).filter(
            and_(
                ChannelPoints.user_id == user_id,
                ChannelPoints.channel_name == channel_name
            )
        ).scalar() or 0

        total_points = self.db.query(func.sum(ChannelPoints.points)).filter(
             and_(
                ChannelPoints.user_id == user_id,
                ChannelPoints.channel_name == channel_name
            )
        ).scalar() or 0
        
        return {"total_users": total_users, "total_points": total_points}

    def add_points_record(self, points: ChannelPoints) -> ChannelPoints:
        self.db.add(points)
        self.db.commit()
        self.db.refresh(points)
        return points

    # === ChannelReward ===

    def get_reward(self, reward_id: int) -> Optional[ChannelReward]:
        return self.db.query(ChannelReward).filter(ChannelReward.id == reward_id).first()

    def get_reward_by_title(self, user_id: int, platform: str, title: str) -> Optional[ChannelReward]:
        return self.db.query(ChannelReward).filter(
            and_(
                ChannelReward.user_id == user_id,
                ChannelReward.platform == platform,
                ChannelReward.title == title
            )
        ).first()

    def get_reward_by_user(self, reward_id: int, user_id: int) -> Optional[ChannelReward]:
        return self.db.query(ChannelReward).filter(
            and_(
                ChannelReward.id == reward_id,
                ChannelReward.user_id == user_id
            )
        ).first()

    def get_active_rewards(self, user_id: int, platform: str = None) -> List[ChannelReward]:
        query = self.db.query(ChannelReward).filter(ChannelReward.user_id == user_id)
        if platform:
            query = query.filter(ChannelReward.platform == platform)
        return query.order_by(ChannelReward.cost).all()
    
    def count_active_rewards(self, user_id: int) -> int:
        return self.db.query(func.count(ChannelReward.id)).filter(
            and_(
                ChannelReward.user_id == user_id,
                ChannelReward.is_enabled
            )
        ).scalar() or 0

    def add_reward(self, reward: ChannelReward) -> ChannelReward:
        self.db.add(reward)
        self.db.commit()
        self.db.refresh(reward)
        return reward
    
    def delete_reward(self, reward: ChannelReward):
        self.db.delete(reward)
        self.db.commit()

    # === RewardQueue ===

    def get_queue_item(self, queue_id: int, user_id: int) -> Optional[RewardQueue]:
        return self.db.query(RewardQueue).filter(
            and_(
                RewardQueue.id == queue_id,
                RewardQueue.user_id == user_id
            )
        ).first()

    def get_pending_queue_item(self, queue_id: int, user_id: int) -> Optional[RewardQueue]:
        return self.db.query(RewardQueue).filter(
            and_(
                RewardQueue.id == queue_id,
                RewardQueue.user_id == user_id,
                RewardQueue.status == 'pending'
            )
        ).first()

    def get_queue_by_user(self, user_id: int, status: str = None) -> List[RewardQueue]:
        query = self.db.query(RewardQueue).filter(RewardQueue.user_id == user_id)
        if status:
            query = query.filter(RewardQueue.status == status)
        return query.order_by(desc(RewardQueue.created_at)).all()
    
    def count_pending_queue(self, user_id: int) -> int:
        return self.db.query(func.count(RewardQueue.id)).filter(
            and_(
                RewardQueue.user_id == user_id,
                RewardQueue.status == 'pending'
            )
        ).scalar() or 0
    
    def count_pending_requests_for_reward(self, reward_id: int) -> int:
         return self.db.query(RewardQueue).filter(
            and_(
                RewardQueue.reward_id == reward_id,
                RewardQueue.status == 'pending'
            )
        ).count()

    def add_queue_item(self, item: RewardQueue) -> RewardQueue:
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item
    
    # === Transactions ===
    
    def add_transaction(self, transaction: PointsTransaction):
        """Add transaction without commit (for batch operations)."""
        self.db.add(transaction)
    
    def create_transaction(
        self,
        user_id: int,
        viewer_id: str,
        viewer_name: str,
        platform: str,
        channel_name: str,
        transaction_type: str,
        amount: int,
        reason: str
    ) -> PointsTransaction:
        """Create and commit a points transaction."""
        transaction = PointsTransaction(
            user_id=user_id,
            viewer_id=viewer_id,
            viewer_name=viewer_name,
            platform=platform,
            channel_name=channel_name,
            transaction_type=transaction_type,
            amount=amount,
            reason=reason
        )
        self.db.add(transaction)
        self.db.commit()
        self.db.refresh(transaction)
        return transaction
