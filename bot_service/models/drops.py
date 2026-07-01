"""Drops and lootbox models."""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from core.datetime_utils import utcnow_naive
from models.base import Base


class DropsType(Base):
    """Drop type definition."""

    __tablename__ = "drops_types"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow_naive)


class DropsQuality(Base):
    """Drop quality definition."""

    __tablename__ = "drops_qualities"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    color = Column(String, nullable=False)
    weight = Column(Integer, default=100)
    created_at = Column(DateTime, default=utcnow_naive)


class DropsConfig(Base):
    """Drops configuration for a channel."""

    __tablename__ = "drops_configs"
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND session_id IS NULL) OR (user_id IS NULL AND session_id IS NOT NULL)",
            name="check_user_or_session_drops_config",
        ),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    session_id = Column(String, nullable=True, index=True)
    channel_name = Column(String, nullable=False, index=True)
    platform = Column(String, nullable=True, default="global")

    # Streak settings.
    streak_days_common = Column(Integer, default=1)
    streak_days_rare = Column(Integer, default=3)
    streak_days_epic = Column(Integer, default=7)
    streak_days_legendary = Column(Integer, default=14)
    streak_messages_required = Column(Integer, default=5)
    streak_reset_on_skip = Column(Boolean, default=True)
    streak_enabled_twitch = Column(Boolean, nullable=False, server_default="false")
    streak_enabled_vk = Column(Boolean, nullable=False, server_default="false")
    streak_enabled = Column(Boolean, default=False)  # Deprecated.

    # Donation settings.
    donation_enabled = Column(Boolean, default=True)
    donation_amount_common = Column(Float, default=50.0)
    donation_amount_rare = Column(Float, default=100.0)
    donation_amount_epic = Column(Float, default=500.0)
    donation_amount_legendary = Column(Float, default=1000.0)

    # Mythical lootbox settings.
    mythical_enabled = Column(Boolean, default=True)
    mythical_min_interval_hours = Column(Integer, default=2)
    mythical_max_interval_hours = Column(Integer, default=8)
    mythical_window_duration_minutes = Column(Integer, default=5)
    mythical_donation_amount = Column(Float, default=2000.0)
    mythical_last_appeared = Column(DateTime, nullable=True)

    # Widget (OBS animation) settings.
    widget_spinning_duration_ms = Column(Integer, default=5000)
    widget_opening_duration_ms = Column(Integer, default=1000)
    widget_result_duration_ms = Column(Integer, default=5500)
    widget_closing_duration_ms = Column(Integer, default=500)
    widget_spin_sound_file = Column(String, nullable=True)
    widget_start_sound_file = Column(String, nullable=True)
    widget_reveal_sound_file = Column(String, nullable=True)
    widget_sound_volume = Column(Float, default=1.0)
    widget_frame_color = Column(String, nullable=True, default="#ff8a00")
    widget_text_color = Column(String, nullable=True, default="#ffffff")
    widget_background_color = Column(String, nullable=True, default="#120821")
    widget_font_scale = Column(Float, default=1.0)
    widget_token = Column(String, nullable=True, unique=True, index=True)

    created_at = Column(DateTime, default=utcnow_naive)
    updated_at = Column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)


class DropsReward(Base):
    """Reward that can be granted by drops."""

    __tablename__ = "drops_rewards"
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND session_id IS NULL) OR (user_id IS NULL AND session_id IS NOT NULL)",
            name="check_user_or_session_drops_reward",
        ),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    session_id = Column(String, nullable=True, index=True)
    channel_name = Column(String, nullable=False, index=True)
    platform = Column(String, nullable=False)

    name = Column(String, nullable=False)
    description = Column(Text)
    quality_id = Column(Integer, ForeignKey("drops_qualities.id"), nullable=False)
    weight = Column(Integer, default=100)

    # Reward payload.
    reward_type = Column(String, nullable=False)
    reward_value = Column(String, nullable=False)

    # Card image for gacha roll UI.
    image_url = Column(String, nullable=True)

    # Reward sound.
    sound_file = Column(String, nullable=True)
    sound_volume = Column(Float, default=1.0)

    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=utcnow_naive)
    updated_at = Column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)


class UserStreak(Base):
    """Viewer streak tracking."""

    __tablename__ = "user_streaks"
    __table_args__ = (
        UniqueConstraint("user_id", "viewer_id", "platform", name="uq_user_streak"),
        UniqueConstraint("session_id", "viewer_id", "platform", name="uq_session_streak"),
        CheckConstraint(
            "(user_id IS NOT NULL AND session_id IS NULL) OR (user_id IS NULL AND session_id IS NOT NULL)",
            name="check_user_or_session_user_streak",
        ),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    session_id = Column(String, nullable=True, index=True)
    channel_name = Column(String, nullable=False, index=True)
    platform = Column(String, nullable=False)
    viewer_id = Column(String, nullable=False, index=True)
    viewer_name = Column(String, nullable=False)

    current_streak = Column(Integer, default=0)
    max_streak = Column(Integer, default=0)
    last_activity = Column(DateTime, default=utcnow_naive)
    messages_this_stream = Column(Integer, default=0)

    # Last stream attendance information.
    last_stream_session_id = Column(Integer, ForeignKey("stream_sessions.id"), nullable=True, index=True)
    last_stream_attended_at = Column(DateTime, nullable=True, index=True)

    created_at = Column(DateTime, default=utcnow_naive)
    updated_at = Column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)


class DropsHistory(Base):
    """Drops reward history."""

    __tablename__ = "drops_history"
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND session_id IS NULL) OR (user_id IS NULL AND session_id IS NOT NULL)",
            name="check_user_or_session_drops_history",
        ),
        UniqueConstraint(
            "user_id",
            "channel_name",
            "platform",
            "source_event_id",
            name="uq_drops_history_user_source_event",
        ),
        UniqueConstraint(
            "session_id",
            "channel_name",
            "platform",
            "source_event_id",
            name="uq_drops_history_session_source_event",
        ),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    session_id = Column(String, nullable=True, index=True)
    channel_name = Column(String, nullable=False, index=True)
    platform = Column(String, nullable=False)
    viewer_id = Column(String, nullable=False, index=True)
    viewer_name = Column(String, nullable=False)

    # Lootbox type.
    lootbox_type = Column(String, nullable=False)
    quality_id = Column(Integer, ForeignKey("drops_qualities.id"), nullable=False)

    # Granted reward.
    reward_id = Column(Integer, ForeignKey("drops_rewards.id"), nullable=True)
    reward_name = Column(String, nullable=False)
    reward_type = Column(String, nullable=False)
    reward_value = Column(String, nullable=False)

    # Additional context.
    donation_amount = Column(Float, nullable=True)
    streak_days = Column(Integer, nullable=True)
    messages_count = Column(Integer, nullable=True)
    stream_session_id = Column(Integer, ForeignKey("stream_sessions.id"), nullable=True, index=True)
    source_event_id = Column(String, nullable=True, index=True)

    # External linkage data.
    donation_alert_id = Column(String, nullable=True)
    chat_message_id = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=utcnow_naive, index=True)


class PendingStreakChest(Base):
    """A viewer streak chest waiting to be opened."""

    __tablename__ = "pending_streak_chests"
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND session_id IS NULL) OR (user_id IS NULL AND session_id IS NOT NULL)",
            name="check_user_or_session_pending_streak_chest",
        ),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    session_id = Column(String, nullable=True, index=True)
    channel_name = Column(String, nullable=False, index=True)
    platform = Column(String, nullable=False, index=True)
    viewer_id = Column(String, nullable=False, index=True)
    viewer_name = Column(String, nullable=False)

    quality_id = Column(Integer, ForeignKey("drops_qualities.id"), nullable=False)
    quality_name = Column(String, nullable=False)
    streak_days = Column(Integer, nullable=False)
    messages_count = Column(Integer, nullable=True)
    source_event_id = Column(String, nullable=True, index=True)
    chat_message_id = Column(Integer, nullable=True)
    stream_session_id = Column(Integer, ForeignKey("stream_sessions.id"), nullable=True, index=True)

    status = Column(String, nullable=False, default="pending", index=True)
    opened_history_id = Column(Integer, ForeignKey("drops_history.id"), nullable=True)
    opened_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=utcnow_naive, index=True)
    updated_at = Column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)


class MemeAlertsGrantHistory(Base):
    """Local history of successful MemeAlerts grants."""

    __tablename__ = "memealerts_grant_history"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    target_user_id = Column(String, nullable=True, index=True)
    target_user_name = Column(String, nullable=True, index=True)
    amount = Column(Integer, nullable=False)
    source = Column(String, nullable=False, default="ui")
    platform = Column(String, nullable=False, default="dashboard")
    channel_name = Column(String, nullable=False, default="dashboard")
    issued_by = Column(String, nullable=True)
    created_at = Column(DateTime, default=utcnow_naive, index=True)


class MythicalDropsSession(Base):
    """Mythical drops session."""

    __tablename__ = "mythical_drops_sessions"
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND session_id IS NULL) OR (user_id IS NULL AND session_id IS NOT NULL)",
            name="check_user_or_session_mythical_drops",
        ),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    session_id = Column(String, nullable=True, index=True)
    channel_name = Column(String, nullable=False, index=True)
    platform = Column(String, nullable=False)

    # Session parameters.
    donation_amount = Column(Float, nullable=False)
    window_duration_minutes = Column(Integer, nullable=False)

    # Runtime state.
    is_active = Column(Boolean, default=True)

    started_at = Column(DateTime, default=utcnow_naive)
    expires_at = Column(DateTime, nullable=False)
    winner_viewer_id = Column(String, nullable=True)
    winner_viewer_name = Column(String, nullable=True)
    winner_donation_amount = Column(Float, nullable=True)

    created_at = Column(DateTime, default=utcnow_naive)


class StreamSession(Base):
    """Tracked stream session start/end boundaries."""

    __tablename__ = "stream_sessions"
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND session_id IS NULL) OR (user_id IS NULL AND session_id IS NOT NULL)",
            name="check_user_or_session_stream_session",
        ),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    session_id = Column(String, nullable=True, index=True)
    channel_name = Column(String, nullable=False, index=True)
    platform = Column(String, nullable=False)

    # Stream timing.
    started_at = Column(DateTime, nullable=False, default=utcnow_naive, index=True)
    ended_at = Column(DateTime, nullable=True, index=True)

    # Stream state.
    is_active = Column(Boolean, default=True, index=True)

    # Additional metadata.
    viewer_count_peak = Column(Integer, default=0)
    title = Column(String, nullable=True)

    created_at = Column(DateTime, default=utcnow_naive)
    updated_at = Column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)
