"""Moderation models for blocked entities and whitelist entries."""

from sqlalchemy import Boolean, Column, DateTime, Integer, String, UniqueConstraint

from core.datetime_utils import utcnow_naive
from models.base import Base


class BlockedBot(Base):
    """Blocked bot account model."""

    __tablename__ = "blocked_bots"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    bot_name = Column(String, unique=True, index=True, nullable=False)
    added_at = Column(DateTime, default=utcnow_naive)


class BlockedChannel(Base):
    """Blocked channel model."""

    __tablename__ = "blocked_channels"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    channel_name = Column(String, unique=True, index=True, nullable=False)
    reason = Column(String, nullable=True)
    blocked_by = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow_naive)


class WhitelistedChannel(Base):
    """Whitelisted channel model."""

    __tablename__ = "whitelisted_channels"
    __table_args__ = (
        UniqueConstraint("channel_name", "platform", name="uix_channel_platform"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    channel_name = Column(String, index=True, nullable=False)
    platform = Column(String, index=True, nullable=False)
    created_at = Column(DateTime, default=utcnow_naive)
