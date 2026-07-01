"""Analytics models for chat activity, progression, and psychology analysis."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text

from models.base import Base


class ChatMessage(Base):
    """Chat messages used for activity tracking."""

    __tablename__ = "chat_messages"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    channel_name = Column(String, nullable=False, index=True)
    platform = Column(String, nullable=False)
    author_username = Column(String, nullable=True, index=True)
    author_id = Column(String, nullable=True, index=True)
    message = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    is_deleted = Column(Boolean, default=False)

    # User role and badge metadata.
    role = Column(String, nullable=True)
    badges = Column(JSON, nullable=True)


class UserProgression(Base):
    """User progression metrics for achievements and streak systems."""

    __tablename__ = "user_progression"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    channel_name = Column(String, nullable=False, index=True)
    platform = Column(String, nullable=False)

    # Activity statistics.
    total_days_active = Column(Integer, default=0)
    current_streak = Column(Integer, default=0)
    longest_streak = Column(Integer, default=0)
    last_activity_date = Column(DateTime)
    total_messages = Column(Integer, default=0)

    # Donation statistics.
    total_donated = Column(Float, default=0.0)
    total_donations_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PsychologyAnalysis(Base):
    """Stored results of psychology analysis runs."""

    __tablename__ = "psychology_analysis"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    target_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    target_username = Column(String, nullable=False)
    platform = Column(String, nullable=False)
    analyzed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    analyzed_by_username = Column(String, nullable=False)
    analysis_text = Column(Text, nullable=False)
    messages_count = Column(Integer, nullable=False)
    analysis_date = Column(DateTime, default=datetime.utcnow, index=True)
    ai_model_used = Column(String, nullable=True)
