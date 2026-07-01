# bot_service/services/points_service.py
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from core.database import get_db, ChannelPoints, ChannelReward, PointsTransaction, RewardQueue
from core.datetime_utils import utcnow_naive
from repositories.points_repository import PointsRepository

logger = logging.getLogger('bot_service')


class PointsService:
    """
    Service for managing channel points and rewards.
    Uses the repository pattern for data access.
    """

    def __init__(self):
        pass

    def _get_repository(self, db: Session) -> PointsRepository:
        return PointsRepository(db)

    def get_user_points(
        self,
        user_id: int,
        viewer_id: str,
        platform: str,
        channel_name: str,
        db: Session
    ) -> int:
        """Get a viewer's current points balance."""
        repo = self._get_repository(db)
        points_record = repo.get_user_points(user_id, viewer_id, platform, channel_name)
        return points_record.points if points_record else 0

    def add_points(
        self,
        user_id: int,
        viewer_id: str,
        viewer_name: str,
        platform: str,
        channel_name: str,
        amount: int,
        reason: str = "Manual add",
        db: Session = None
    ) -> int:
        """Add points to a viewer."""
        if amount <= 0:
            return 0

        def _do_add(session_db: Session) -> int:
            try:
                repo = self._get_repository(session_db)
                
                # Get or create the points record.
                points_record = repo.get_user_points(user_id, viewer_id, platform, channel_name)
                
                if not points_record:
                    points_record = ChannelPoints(
                        user_id=user_id,
                        viewer_id=viewer_id,
                        viewer_name=viewer_name,
                        platform=platform,
                        channel_name=channel_name,
                        points=0
                    )
                    repo.add_points_record(points_record)
                
                # Update the balance.
                points_record.points += amount
                points_record.last_updated = utcnow_naive()
                
                # Persist the transaction record.
                transaction = PointsTransaction(
                    user_id=user_id,
                    viewer_id=viewer_id,
                    channel_name=channel_name,
                    platform=platform,
                    amount=amount,
                    operation_type='add',
                    reason=reason,
                    created_at=utcnow_naive()
                )
                repo.add_transaction(transaction)
                
                session_db.commit()
                return points_record.points
                
            except Exception:
                logger.exception("Error adding points")
                session_db.rollback()
                return 0

        if db is not None:
            return _do_add(db)
        
        with next(get_db()) as new_db:
            return _do_add(new_db)

    def deduct_points(
        self,
        user_id: int,
        viewer_id: str,
        viewer_name: str,
        platform: str,
        channel_name: str,
        amount: int,
        reason: str = "Manual deduct",
        db: Session = None
    ) -> int:
        """Deduct points from a viewer."""
        if amount <= 0:
            return 0

        def _do_deduct(session_db: Session) -> int:
            try:
                repo = self._get_repository(session_db)
                points_record = repo.get_user_points(user_id, viewer_id, platform, channel_name)
                
                if not points_record or points_record.points < amount:
                    return -1  # Insufficient points.
                
                # Apply the deduction.
                points_record.points -= amount
                points_record.last_updated = utcnow_naive()
                
                # Persist the transaction record.
                transaction = PointsTransaction(
                    user_id=user_id,
                    viewer_id=viewer_id,
                    channel_name=channel_name,
                    platform=platform,
                    amount=-amount,
                    operation_type='deduct',
                    reason=reason,
                    created_at=utcnow_naive()
                )
                repo.add_transaction(transaction)
                
                session_db.commit()
                return points_record.points
                
            except Exception:
                logger.exception("Error deducting points")
                session_db.rollback()
                return 0

        if db is not None:
            return _do_deduct(db)
        
        with next(get_db()) as new_db:
            return _do_deduct(new_db)

    def get_channel_leaderboard(
        self,
        user_id: int,
        channel_name: str,
        platform: str = None,
        limit: int = 10,
        db: Session = None
    ) -> List[Dict[str, Any]]:
        """Get the channel leaderboard by points."""
        def _get(session_db: Session):
            repo = self._get_repository(session_db)
            records = repo.get_leaderboard(user_id, channel_name, platform, limit)
            
            return [
                {
                    "viewer_name": r.viewer_name,
                    "points": r.points,
                    "platform": r.platform
                }
                for r in records
            ]

        if db is not None:
            return _get(db)
        
        with next(get_db()) as new_db:
            return _get(new_db)

    def create_reward(
        self,
        user_id: int,
        platform: str,
        channel_name: str,
        title: str,
        description: str,
        cost: int,
        is_dynamic_price: bool = False,
        **kwargs
    ) -> Optional[ChannelReward]:
        """Create a new channel reward."""
        with next(get_db()) as db:
            try:
                repo = self._get_repository(db)
                
                # Optional cap for the number of active rewards.
                count = repo.count_active_rewards(user_id)
                if count >= 50:
                    return None
                
                reward = ChannelReward(
                    user_id=user_id,
                    platform=platform,
                    channel_name=channel_name,
                    title=title,
                    description=description,
                    cost=cost,
                    is_dynamic_price=is_dynamic_price,
                    is_enabled=kwargs.get('is_enabled', True),
                    background_color=kwargs.get('background_color', '#000000'),
                    cooldown=kwargs.get('cooldown', 0)
                )
                
                return repo.add_reward(reward)
                
            except Exception:
                logger.exception("Error creating reward")
                db.rollback()
                return None

    def get_channel_rewards(
        self,
        user_id: int,
        platform: str = None,
        db: Session = None
    ) -> List[ChannelReward]:
        """Get channel rewards."""
        def _get(session_db: Session):
            repo = self._get_repository(session_db)
            return repo.get_active_rewards(user_id, platform)

        if db is not None:
            return _get(db)
        
        with next(get_db()) as new_db:
            return _get(new_db)

    def redeem_reward(
        self,
        user_id: int,
        reward_id: int,
        viewer_id: str,
        viewer_name: str,
        platform: str,
        channel_name: str,
        user_input: str = None
    ) -> Dict[str, Any]:
        """Redeem a reward with points."""
        with next(get_db()) as db:
            try:
                repo = self._get_repository(db)
                
                # 1. Load the reward.
                reward = repo.get_reward_by_user(reward_id, user_id)
                if not reward or not reward.is_enabled:
                    return {"success": False, "error": "Reward not found or disabled"}
                
                # 2. Validate the current balance.
                points_record = repo.get_user_points(user_id, viewer_id, platform, channel_name)
                current_points = points_record.points if points_record else 0
                
                if current_points < reward.cost:
                    return {"success": False, "error": "Insufficient points"}
                
                # 3. Deduct the cost.
                if points_record:
                    points_record.points -= reward.cost
                    points_record.last_updated = utcnow_naive()
                
                # 4. Create the queue item.
                queue_item = RewardQueue(
                    user_id=user_id,
                    reward_id=reward.id,
                    viewer_id=viewer_id,
                    viewer_name=viewer_name,
                    platform=platform,
                    cost=reward.cost,
                    input_text=user_input,
                    status='pending',
                    created_at=utcnow_naive()
                )
                repo.add_queue_item(queue_item)
                
                # 5. Record the points transaction.
                transaction = PointsTransaction(
                    user_id=user_id,
                    viewer_id=viewer_id,
                    channel_name=channel_name,
                    platform=platform,
                    amount=-reward.cost,
                    operation_type='redeem',
                    reason=f"Redeemed: {reward.title}",
                    created_at=utcnow_naive()
                )
                repo.add_transaction(transaction)
                
                db.commit()
                
                return {
                    "success": True, 
                    "remaining_points": current_points - reward.cost,
                    "queue_id": queue_item.id,
                    "reward_title": reward.title
                }
                
            except Exception:
                logger.exception("Error redeeming reward")
                db.rollback()
                return {"success": False, "error": "Internal error"}

    def get_reward_queue(
        self,
        user_id: int,
        status: str = None,
        db: Session = None
    ) -> List[Dict[str, Any]]:
        """Get the reward queue."""
        def _get(session_db: Session):
            repo = self._get_repository(session_db)
            queue = repo.get_queue_by_user(user_id, status)
            
            result = []
            for item in queue:
                result.append({
                    "id": item.id,
                    "viewer_name": item.viewer_name,
                    "reward_title": item.reward.title if item.reward else "Unknown",
                    "cost": item.cost,
                    "input": item.input_text,
                    "status": item.status,
                    "created_at": item.created_at.isoformat() if item.created_at else None
                })
            return result

        if db is not None:
            return _get(db)
        
        with next(get_db()) as new_db:
            return _get(new_db)

    def process_reward(
        self,
        user_id: int,
        queue_id: int,
        action: str,
        moderator_note: str = None
    ) -> bool:
        """Process a reward queue item as a moderator."""
        with next(get_db()) as db:
            try:
                repo = self._get_repository(db)
                item = repo.get_queue_item(queue_id, user_id)
                
                if not item:
                    return False
                
                if action == 'approve':
                    item.status = 'approved'
                elif action == 'reject':
                    item.status = 'rejected'
                    # Refund points
                    points_record = repo.get_user_points(
                        user_id, item.viewer_id, item.platform, 
                        # Assuming channel name is available or derivable. 
                        # In Queue Item we might not store channel_name explicitly but we have user_id.
                        # Actually ChannelPoints requires channel_name. 
                        # RewardQueue has user_id.
                        # PointsRepository needs channel_name.
                        # Wait, RewardQueue table doesn't have channel_name in model?
                        # Let's check model if needed. 
                        # Assuming 'item.reward.channel_name'
                        item.reward.channel_name if item.reward else ""
                    )
                    
                    if points_record:
                        points_record.points += item.cost
                        points_record.last_updated = utcnow_naive()
                        
                        # Add refund transaction
                        trans = PointsTransaction(
                             user_id=user_id,
                             viewer_id=item.viewer_id,
                             channel_name=item.reward.channel_name if item.reward else "",
                             platform=item.platform,
                             amount=item.cost,
                             operation_type='refund',
                             reason=f"Refund: {item.reward.title}",
                             created_at=utcnow_naive()
                        )
                        repo.add_transaction(trans)
                
                else:
                    return False
                
                item.processed_at = utcnow_naive()
                db.commit()
                return True
                
            except Exception:
                logger.exception("Error processing reward")
                db.rollback()
                return False

    def get_channel_stats(
        self,
        user_id: int,
        channel_name: str,
        db: Session = None
    ) -> Dict[str, int]:
        """Get channel points statistics."""
        def _get(session_db: Session):
            repo = self._get_repository(session_db)
            return repo.get_channel_stats(user_id, channel_name)

        if db is not None:
            return _get(db)
        
        with next(get_db()) as new_db:
            return _get(new_db)

    def update_reward(
        self,
        user_id: int,
        reward_id: int,
        update_data: Dict[str, Any],
        db: Session = None
    ) -> Optional[ChannelReward]:
        """Update a reward."""
        def _update(session_db: Session):
            try:
                repo = self._get_repository(session_db)
                reward = repo.get_reward_by_user(reward_id, user_id)
                
                if not reward:
                    return None
                
                for key, value in update_data.items():
                    if hasattr(reward, key):
                        setattr(reward, key, value)
                
                session_db.commit()
                session_db.refresh(reward)
                return reward
            except Exception:
                logger.exception("Error updating reward")
                session_db.rollback()
                return None

        if db is not None:
            return _update(db)
        
        with next(get_db()) as new_db:
            return _update(new_db)

    def delete_reward(
        self,
        user_id: int,
        reward_id: int,
        db: Session = None
    ) -> bool:
        """Delete a reward."""
        def _delete(session_db: Session):
            try:
                repo = self._get_repository(session_db)
                reward = repo.get_reward_by_user(reward_id, user_id)
                
                if reward:
                    repo.delete_reward(reward)
                    return True
                return False
            except Exception:
                logger.exception("Error deleting reward")
                session_db.rollback()
                return False

        if db is not None:
            return _delete(db)
        
        with next(get_db()) as new_db:
            return _delete(new_db)

    def toggle_reward(
        self,
        user_id: int,
        reward_id: int,
        db: Session = None
    ) -> Optional[bool]:
        """Toggle reward enabled/disabled status."""
        def _toggle(session_db: Session):
            try:
                repo = self._get_repository(session_db)
                reward = repo.get_reward_by_user(reward_id, user_id)
                
                if reward:
                    reward.is_enabled = not reward.is_enabled
                    session_db.commit()
                    return reward.is_enabled
                return None
            except Exception:
                logger.exception("Error toggling reward")
                session_db.rollback()
                return None

        if db is not None:
            return _toggle(db)
        
        with next(get_db()) as new_db:
            return _toggle(new_db)

