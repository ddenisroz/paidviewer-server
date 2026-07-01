"""OBS widget models."""

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint

from core.datetime_utils import utcnow_naive
from models.base import Base


class ChatBoxSettings(Base):
    """ChatBox customization settings for the OBS widget."""

    __tablename__ = "chatbox_settings"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_chatbox_user"),
        UniqueConstraint("widget_token", name="uq_chatbox_token"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    widget_token = Column(String, nullable=False, unique=True, index=True)

    # Font settings.
    font_family = Column(String, default="Inter")
    font_size = Column(Integer, default=16)
    font_weight = Column(String, default="normal")
    text_stroke_width = Column(Integer, default=0)
    text_stroke_color = Column(String, default="#000000")

    # Background settings.
    background_color = Column(String, default="#000000")
    background_opacity = Column(Float, default=0.5)

    # Display settings.
    max_messages = Column(Integer, default=20)
    chat_direction = Column(String, default="vertical")
    chat_width = Column(Integer, default=100)
    show_platform_icons = Column(Boolean, default=True)
    show_roles = Column(Boolean, default=False)
    show_badges = Column(Boolean, default=True)

    # Text colors.
    text_color = Column(String, default="#FFFFFF")
    username_color = Column(String, default="#9147FF")

    # Additional settings.
    message_spacing = Column(Integer, default=4)
    border_radius = Column(Integer, default=8)
    animation_duration = Column(Integer, default=300)
    animation_type = Column(String, default="fade")
    message_fade_seconds = Column(Integer, default=60)

    # 7TV emotes, links, and images.
    show_7tv_emotes = Column(Boolean, default=True)
    show_links = Column(Boolean, default=True)
    auto_load_images = Column(Boolean, default=True)
    separate_message_backgrounds = Column(Boolean, default=True)
    message_background_mode = Column(String, default="message")

    created_at = Column(DateTime, default=utcnow_naive)
    updated_at = Column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)
