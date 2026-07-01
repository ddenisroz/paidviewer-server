"""TTS settings and related models."""

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)

from core.datetime_utils import utcnow_naive
from models.base import Base


class TTSUserSettings(Base):
    """Base TTS settings for users."""

    __tablename__ = "tts_user_settings"
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND session_id IS NULL) OR (user_id IS NULL AND session_id IS NOT NULL)",
            name="check_user_or_session",
        ),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, unique=True)
    session_id = Column(String, nullable=True, unique=True)

    # Core TTS settings.
    engine = Column(String, nullable=False, default="gtts")
    voice = Column(String, nullable=False, default="default_voice")
    listening_mode = Column(String, nullable=False, default="website")
    advanced_provider = Column(String, nullable=False, default="f5")
    f5_mode = Column(String, nullable=False, default="cloud")
    gcloud_voices = Column(JSON, nullable=False, default=list)
    gcloud_mood = Column(String, nullable=False, default="neutral")

    # Enabled platforms for playback.
    enabled_platforms = Column(JSON, nullable=False, default=list)

    # TTS execution mode.
    tts_mode = Column(String, nullable=False, default="all_messages")
    tts_reward_ids = Column(JSON, nullable=False, default=lambda: {})

    # Emoji and smiley filters.
    enable_7tv = Column(Boolean, nullable=False, default=False)
    enable_twitch = Column(Boolean, nullable=False, default=False)
    enable_lexicon_filter = Column(Boolean, nullable=False, default=True)
    enable_custom_lexicon = Column(Boolean, nullable=False, default=False)

    # Additional behavior settings.
    max_message_length = Column(Integer, nullable=False, default=150)
    skip_commands = Column(Boolean, nullable=False, default=True)
    use_local_tts = Column(Boolean, nullable=False, default=False)

    # Message filters.
    filter_replies = Column(Boolean, nullable=False, default=False)
    filter_mentions = Column(Boolean, nullable=False, default=False)
    filter_banwords = Column(Boolean, nullable=False, default=True)
    disable_voice_selection = Column(Boolean, nullable=False, default=False)
    speak_sender_name = Column(Boolean, nullable=False, default=False)

    # YouTube playback settings.
    youtube_settings = Column(JSON, nullable=False, default=lambda: {"playback_mode": "browser", "volume_level": 100})

    created_at = Column(DateTime, default=utcnow_naive)
    updated_at = Column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)


class TTSBlockedUser(Base):
    """Users blocked from TTS playback."""

    __tablename__ = "tts_blocked_users"
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND session_id IS NULL) OR (user_id IS NULL AND session_id IS NOT NULL)",
            name="check_user_or_session_tts_blocked_user",
        ),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    session_id = Column(String, nullable=True, index=True)
    channel_name = Column(String, nullable=False, index=True)
    platform = Column(String, nullable=False)
    username = Column(String, nullable=False)
    blocked_at = Column(DateTime, default=utcnow_naive)
    blocked_by = Column(Integer, nullable=True)
    reason = Column(String, nullable=True)


class FilteredWord(Base):
    """Blocked words for TTS filtering."""

    __tablename__ = "filtered_words"
    __table_args__ = (
        Index("idx_user_word", "user_id", "word"),
        Index("idx_session_word", "session_id", "word"),
        Index("idx_platform", "platform"),
        Index("idx_active", "is_active"),
        UniqueConstraint("user_id", "word", "platform", name="uq_user_word_platform"),
        UniqueConstraint("session_id", "word", "platform", name="uq_session_word_platform"),
        CheckConstraint(
            "(user_id IS NOT NULL AND session_id IS NULL) OR (user_id IS NULL AND session_id IS NOT NULL)",
            name="check_user_or_session_filtered_word",
        ),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    session_id = Column(String, nullable=True, index=True)
    word = Column(String, nullable=False, index=True)
    platform = Column(String, nullable=False, default="all")
    created_at = Column(DateTime, default=utcnow_naive, index=True)
    is_active = Column(Boolean, default=True)


class LocalTTSEndpoint(Base):
    """Local TTS endpoint configuration model."""

    __tablename__ = "local_tts_endpoints"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_local_tts_endpoints_user_provider"),
        UniqueConstraint("session_id", "provider", name="uq_local_tts_endpoints_session_provider"),
        CheckConstraint(
            "(user_id IS NOT NULL AND session_id IS NULL) OR (user_id IS NULL AND session_id IS NOT NULL)",
            name="check_user_or_session_local_tts",
        ),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    session_id = Column(String, nullable=True, index=True)

    # Endpoint configuration.
    provider = Column(String, nullable=False, default="f5", index=True)
    endpoint_url = Column(String, nullable=False)
    api_key = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    use_local = Column(Boolean, default=False)

    # Health and monitoring.
    last_health_check = Column(DateTime, nullable=True)
    is_healthy = Column(Boolean, default=False)
    health_check_failures = Column(Integer, default=0)

    # Metadata.
    tts_version = Column(String, nullable=True)
    gpu_info = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=utcnow_naive)
    updated_at = Column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)


class AudioSettings(Base):
    """Audio volume settings for users."""

    __tablename__ = "audio_settings"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    website_volume = Column(Integer, nullable=False, default=50)
    obs_volume = Column(Integer, nullable=False, default=50)
    created_at = Column(DateTime, default=utcnow_naive)
    updated_at = Column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)


class UserVoiceSettings(Base):
    """Personal settings for voices, both custom and global."""

    __tablename__ = "user_voice_settings"
    __table_args__ = (
        UniqueConstraint("user_id", "voice_id", "tts_provider", name="uq_user_voice_settings"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    voice_id = Column(Integer, nullable=False, index=True)
    voice_name = Column(String, nullable=False)
    tts_provider = Column(String, nullable=False, default="f5", index=True)

    # Personal settings for this voice.
    cfg_strength = Column(Float, nullable=True)
    speed_preset = Column(String, nullable=True)
    volume = Column(Float, nullable=True)

    created_at = Column(DateTime, default=utcnow_naive)
    updated_at = Column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)
