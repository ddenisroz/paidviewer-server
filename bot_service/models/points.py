"""Channel points models."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from core.datetime_utils import utcnow_naive
from models.base import Base


class ChannelPoints(Base):
    """Stored channel points balances for viewers."""

    __tablename__ = "channel_points"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    viewer_id = Column(String, nullable=False, index=True)
    viewer_name = Column(String, nullable=False)
    platform = Column(String, nullable=False)
    channel_name = Column(String, nullable=False, index=True)
    points = Column(Integer, nullable=False, default=0)
    total_earned = Column(Integer, nullable=False, default=0)
    total_spent = Column(Integer, nullable=False, default=0)
    last_activity = Column(DateTime, default=utcnow_naive)
    created_at = Column(DateTime, default=utcnow_naive)


class ChannelReward(Base):
    """Channel point rewards configured by a user."""

    __tablename__ = "channel_rewards"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    platform = Column(String, nullable=False)
    channel_name = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    cost = Column(Integer, nullable=False)
    icon_url = Column(String, nullable=True)
    background_color = Column(String, nullable=True)
    is_enabled = Column(Boolean, default=True)
    is_user_input_required = Column(Boolean, default=False)
    max_per_stream = Column(Integer, nullable=True)
    max_per_user_per_stream = Column(Integer, nullable=True)
    cooldown_expires_at = Column(DateTime, nullable=True)
    prompt = Column(String, nullable=True)
    reward_type = Column(String, nullable=False, default="custom")
    created_at = Column(DateTime, default=utcnow_naive)
    updated_at = Column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)


class PointsTransaction(Base):
    """Channel points transaction log."""

    __tablename__ = "points_transactions"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    viewer_id = Column(String, nullable=False, index=True)
    viewer_name = Column(String, nullable=False)
    platform = Column(String, nullable=False)
    channel_name = Column(String, nullable=False, index=True)
    transaction_type = Column(String, nullable=False)
    amount = Column(Integer, nullable=False)
    reason = Column(String, nullable=True)
    reward_id = Column(Integer, ForeignKey("channel_rewards.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class RewardQueue(Base):
    """Pending reward queue for moderator processing."""

    __tablename__ = "reward_queue"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reward_id = Column(Integer, ForeignKey("channel_rewards.id"), nullable=False)
    viewer_id = Column(String, nullable=False, index=True)
    viewer_name = Column(String, nullable=False)
    platform = Column(String, nullable=False)
    channel_name = Column(String, nullable=False, index=True)
    user_input = Column(String, nullable=True)
    status = Column(String, nullable=False, default="pending")
    points_cost = Column(Integer, nullable=False)
    moderator_note = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    processed_at = Column(DateTime, nullable=True)

    user = relationship("User")
    reward = relationship("ChannelReward")
