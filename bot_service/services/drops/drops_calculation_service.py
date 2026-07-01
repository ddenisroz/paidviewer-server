# features/drops/drops_calculation_service.py
"""Service for calculating drops results with probability-based logic"""
import logging
import random
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session

from core.database import DropsReward

logger = logging.getLogger(__name__)


class DropsCalculationService:
    """Service for calculating drops results with probability-based logic
    
    This service separates business logic (probability calculation) from UI (animation widget).
    All drop results are calculated on the backend before being sent to the frontend.
    """

    def __init__(self, db: Session):
        self.db = db

    def calculate_drop(
        self,
        user_id: int,
        channel_name: str,
        platform: str,
        quality_name: str
    ) -> Optional[Dict[str, Any]]:
        """Calculate a drop result based on quality"""
        logger.info(f"[DICE] [DROPS CALC] Calculating drop for {channel_name} (quality: {quality_name})")

        # Get quality by name
        # Get quality by name
        from repositories.drops_reward_repository import DropsRewardRepository
        reward_repo = DropsRewardRepository(self.db)
        
        quality = reward_repo.get_quality_by_name(quality_name)

        if not quality:
            logger.error(f"[ERROR] [DROPS CALC] Quality '{quality_name}' not found")
            raise ValueError(f"Quality '{quality_name}' not found")

        # Get all active rewards for this quality
        # [NOTE] user_id should be channel owner's id.
        # Get all active rewards for this quality
        # [NOTE] user_id should be channel owner's id.
        rewards = reward_repo.get_by_user_and_channel(
            user_id=user_id,
            channel_name=channel_name,
            quality_id=quality.id
        )
        # Filter active only (get_by_user_and_channel returns all, we need active)
        # Wait, get_by_user_and_channel in repo does NOT filter active.
        # Let's filter here or use a better method.
        rewards = [r for r in rewards if r.is_active]

        if not rewards:
            logger.error(f"[ERROR] [DROPS CALC] No rewards found for quality '{quality_name}'")
            raise ValueError(f"No rewards available for quality '{quality_name}'")

        # Calculate weighted random selection
        selected_reward = self._weighted_random_choice(rewards)

        if not selected_reward:
            logger.error("[ERROR] [DROPS CALC] Failed to select reward")
            raise ValueError("Failed to select reward")

        logger.info(
            f"[OK] [DROPS CALC] Selected reward: {selected_reward.name} "
            f"(weight: {selected_reward.weight}, quality: {quality_name})"
        )

        return {
            "reward_id": selected_reward.id,
            "reward_name": selected_reward.name,
            "reward_type": selected_reward.reward_type,
            "reward_value": selected_reward.reward_value,
            "quality": quality_name,
            "quality_color": quality.color,
            "image_url": selected_reward.image_url,
            "sound_file": selected_reward.sound_file,
            "sound_volume": selected_reward.sound_volume,
            "description": selected_reward.description
        }

    def get_probabilities(
        self,
        user_id: int,
        channel_name: str,
        quality_name: str
    ) -> Dict[str, float]:
        """Get probability distribution for rewards of a given quality"""
        logger.debug(f"[STATS] [DROPS CALC] Getting probabilities for {channel_name} (quality: {quality_name})")

        from repositories.drops_reward_repository import DropsRewardRepository
        reward_repo = DropsRewardRepository(self.db)
        quality = reward_repo.get_quality_by_name(quality_name)

        if not quality:
            logger.warning(f"[WARN] [DROPS CALC] Quality '{quality_name}' not found")
            return {}

        rewards = reward_repo.get_by_user_and_channel(
            user_id=user_id,
            channel_name=channel_name,
            quality_id=quality.id
        )
        rewards = [r for r in rewards if r.is_active]

        if not rewards:
            logger.warning(f"[WARN] [DROPS CALC] No rewards found for quality '{quality_name}'")
            return {}

        total_weight = sum(reward.weight for reward in rewards)

        if total_weight == 0:
            logger.warning("[WARN] [DROPS CALC] Total weight is 0, using uniform distribution")
            uniform_prob = 1.0 / len(rewards)
            return {reward.id: uniform_prob for reward in rewards}

        probabilities = {
            reward.id: reward.weight / total_weight
            for reward in rewards
        }

        logger.debug(f"[STATS] [DROPS CALC] Probabilities: {probabilities}")

        return probabilities

    def validate_probabilities(
        self,
        user_id: int,
        channel_name: str,
        quality_name: str
    ) -> Tuple[bool, Optional[str]]:
        """Validate that probabilities sum to 1.0 and all rewards have valid weights"""
        logger.debug(f"[DROPS CALC] Validating probabilities for {channel_name} (quality: {quality_name})")

        from repositories.drops_reward_repository import DropsRewardRepository
        reward_repo = DropsRewardRepository(self.db)
        quality = reward_repo.get_quality_by_name(quality_name)

        if not quality:
            return False, f"Quality '{quality_name}' not found"

        rewards = reward_repo.get_by_user_and_channel(
            user_id=user_id,
            channel_name=channel_name,
            quality_id=quality.id
        )
        rewards = [r for r in rewards if r.is_active]

        if not rewards:
            return False, f"No rewards found for quality '{quality_name}'"

        invalid_weights = [r for r in rewards if r.weight <= 0]
        if invalid_weights:
            reward_names = [r.name for r in invalid_weights]
            return False, f"Rewards with invalid weights (<=0): {', '.join(reward_names)}"

        total_weight = sum(reward.weight for reward in rewards)

        if total_weight == 0:
            return False, "Total weight is 0"

        probabilities = self.get_probabilities(user_id, channel_name, quality_name)
        total_probability = sum(probabilities.values())

        if not (0.99 <= total_probability <= 1.01):
            return False, f"Probabilities sum to {total_probability:.4f}, expected 1.0"

        logger.debug(f"[OK] [DROPS CALC] Probabilities valid for {channel_name} (quality: {quality_name})")

        return True, None

    def _weighted_random_choice(self, rewards: List[DropsReward]) -> Optional[DropsReward]:
        """Select a random reward based on weights"""
        if not rewards:
            return None

        total_weight = sum(reward.weight for reward in rewards)

        if total_weight == 0:
            logger.warning("[WARN] [DROPS CALC] Total weight is 0, using uniform distribution")
            return random.choice(rewards)

        random_value = random.random() * total_weight
        current_weight = 0

        for reward in rewards:
            current_weight += reward.weight
            if random_value < current_weight:
                logger.debug(
                    f"[TARGET] [DROPS CALC] Selected '{reward.name}' "
                    f"(weight={reward.weight}/{total_weight}, random={random_value:.2f})"
                )
                return reward

        logger.warning("[WARN] [DROPS CALC] Fallback to last reward")
        return rewards[-1]
