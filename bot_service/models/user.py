"""User, session, and token models."""

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, text

from core.datetime_utils import utcnow_naive
from models.base import Base


class User(Base):
    """Unified user account model for the application."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("twitch_username", name="uq_user_twitch_username"),
        UniqueConstraint("vk_username", name="uq_user_vk_username"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    # Application role (admin, user).
    role = Column(String, default="user", nullable=False, index=True)

    # Platform-specific roles (Twitch).
    twitch_is_broadcaster = Column(Boolean, default=False)
    twitch_is_moderator = Column(Boolean, default=False)
    twitch_is_vip = Column(Boolean, default=False)
    twitch_is_subscriber = Column(Boolean, default=False)

    # Platform-specific roles (VK).
    vk_is_owner = Column(Boolean, default=False)
    vk_is_moderator = Column(Boolean, default=False)

    obs_token = Column(String, nullable=True)
    tts_dock_token = Column(String, nullable=True)
    tts_source_token = Column(String, nullable=True)
    is_blocked = Column(Boolean, default=False)
    blocked_reason = Column(String, nullable=True)
    blocked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow_naive)

    # Platform usernames.
    twitch_username = Column(String, nullable=True, unique=True)
    vk_username = Column(String, nullable=True, unique=True)
    vk_channel_name = Column(String, nullable=True, unique=True)

    # DonationAlerts integration.
    donationalerts_user_id = Column(String, nullable=True)
    donationalerts_access_token = Column(String, nullable=True)
    donationalerts_refresh_token = Column(String, nullable=True)

    # TTS-related settings.
    tts_listening_mode = Column(String, default="website")
    tts_enabled = Column(Boolean, default=False)
    donationalerts_token_expires = Column(DateTime, nullable=True)
    temp_oauth_state = Column(String, nullable=True)

    # UI field combination settings.
    combine_titles = Column(Boolean, default=False)
    combine_categories = Column(Boolean, default=False)


class UserSettings(Base):
    """User interface settings model."""

    __tablename__ = "user_settings"
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND session_id IS NULL) OR (user_id IS NULL AND session_id IS NOT NULL)",
            name="check_user_or_session_settings",
        ),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, unique=True)
    session_id = Column(String, nullable=True, unique=True)

    # Chat settings.
    chat_enabled = Column(Boolean, default=True)
    chat_max_messages = Column(Integer, default=50)
    chat_show_timestamps = Column(Boolean, default=True)
    chat_show_platform = Column(Boolean, default=True)
    chat_show_user_roles = Column(Boolean, default=True)
    chat_animation_duration = Column(Integer, default=500)
    chat_animation_type = Column(String, default="slide")
    chat_message_fade_seconds = Column(Integer, default=60)

    # Platform channels for bot connectivity.
    channel_name = Column(String, nullable=True)
    vk_channel_name = Column(String, nullable=True)

    # OBS chat settings.
    obs_width = Column(Integer, default=400)
    obs_height = Column(Integer, default=300)
    obs_font_size = Column(Integer, default=14)
    obs_font_family = Column(String, default="Arial")
    obs_font_weight = Column(String, default="normal")
    obs_background_color = Column(String, default="#000000")
    obs_background_image = Column(String, nullable=True)
    obs_text_color = Column(String, default="#ffffff")
    obs_border_radius = Column(Integer, default=8)
    obs_border_color = Column(String, default="#333333")
    obs_border_width = Column(Integer, default=1)
    obs_message_bg = Column(String, default="#1a1a1a")
    obs_message_border_radius = Column(Integer, default=4)
    obs_message_margin = Column(Integer, default=2)
    obs_message_padding = Column(Integer, default=8)

    # OBS role colors.
    obs_moderator_color = Column(String, default="#00ff00")
    obs_vip_color = Column(String, default="#ffd700")
    obs_subscriber_color = Column(String, default="#ff6b6b")
    obs_normal_color = Column(String, default="#ffffff")

    # UI field combination settings only.
    combine_titles = Column(Boolean, default=False)
    combine_categories = Column(Boolean, default=False)

    # Metadata.
    created_at = Column(DateTime, default=utcnow_naive)
    updated_at = Column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)
    bot_last_welcome_at = Column(DateTime, nullable=True)


class UserToken(Base):
    """OAuth tokens for linked user platforms.

    Only full OAuth authorization is used in runtime (`auth_type` is always `full`).
    """

    __tablename__ = "user_tokens"
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND session_id IS NULL) OR (user_id IS NULL AND session_id IS NOT NULL)",
            name="check_user_or_session_token",
        ),
        Index(
            "uq_user_tokens_platform_identity",
            "platform",
            "platform_user_id",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
            sqlite_where=text("user_id IS NOT NULL"),
        ),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    session_id = Column(String, nullable=True, index=True)
    platform = Column(String, nullable=False)
    platform_user_id = Column(String, nullable=False)
    avatar_url = Column(String, nullable=True)
    access_token = Column(String, nullable=False)
    refresh_token = Column(String, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    scopes = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True)
    auth_type = Column(String, nullable=False, default="full", index=True)
    created_at = Column(DateTime, default=utcnow_naive)
    updated_at = Column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)


class UserSession(Base):
    """Active user session model tied to a unified user_id."""

    __tablename__ = "user_sessions"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_id = Column(String, unique=True, index=True, nullable=False)
    device_info = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utcnow_naive)
    last_activity = Column(DateTime, default=utcnow_naive)
    is_active = Column(Boolean, default=True)


class AdminUser(Base):
    """Administrator model."""

    __tablename__ = "admin_users"
    __table_args__ = (
        UniqueConstraint("platform", "platform_user_id", name="uq_admin_platform_user"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String, nullable=False)
    platform_user_id = Column(String, nullable=False)
    username = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    permissions = Column(JSON, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow_naive)
    updated_at = Column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)
