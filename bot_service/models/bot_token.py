"""Bot token model with refresh-token support."""

from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String

from core.datetime_utils import utcnow_naive
from models.base import Base


class BotToken(Base):
    """OAuth bot token model for Twitch and VK bot accounts.

    Unlike `UserToken`, this model stores tokens for the bot accounts themselves,
    which are used to connect bots to chat runtimes.
    """

    __tablename__ = "bot_tokens"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)

    # Platform identifier (`twitch`, `vk`).
    platform = Column(String, nullable=False, unique=True, index=True)

    # Stored encrypted tokens.
    access_token = Column(String, nullable=False)
    refresh_token = Column(String, nullable=True)

    # Token metadata.
    expires_at = Column(DateTime, nullable=True)
    scopes = Column(JSON, nullable=True)

    # Bot identity metadata.
    bot_user_id = Column(String, nullable=True)
    bot_login = Column(String, nullable=True)

    # Lifecycle metadata.
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow_naive)
    updated_at = Column(DateTime, default=utcnow_naive, onupdate=utcnow_naive)

    def __repr__(self):
        return f"<BotToken(platform='{self.platform}', bot_login='{self.bot_login}')>"
