# core/database.py
"""
Compatibility facade for database model imports.

All models live under ``bot_service/models/``. This module re-exports them for
older imports that still use ``core.database``.

For new code, prefer importing directly from ``models``:
    from models import User, get_db
    from models.user import User, UserSettings
    from models.base import db_session
"""

# Re-export everything from ``models`` for backward compatibility.
from models import (
    # Base and infrastructure
    Base,
    engine,
    SessionLocal,
    get_db,
    db_session,
    init_db,
    DATABASE_URL,
    IS_POSTGRESQL,
    # Users
    User,
    UserSettings,
    UserSession,
    UserToken,
    AdminUser,
    # TTS
    TTSUserSettings,
    TTSBlockedUser,
    FilteredWord,
    LocalTTSEndpoint,
    AudioSettings,
    UserVoiceSettings,
    Worker,
    WorkerPairingToken,
    TTSJob,
    TTSJobAttempt,
    # YouTube
    YouTubeQueue,
    # Points
    ChannelPoints,
    ChannelReward,
    PointsTransaction,
    RewardQueue,
    # Commands
    BotCommand,
    CommandInvocation,
    # Moderation
    BlockedBot,
    BlockedChannel,
    WhitelistedChannel,
    # Analytics
    PsychologyAnalysis,
    ChatMessage,
    UserProgression,
    # Drops
    DropsType,
    DropsQuality,
    DropsConfig,
    DropsReward,
    UserStreak,
    DropsHistory,
    MemeAlertsGrantHistory,
    MythicalDropsSession,
    PendingStreakChest,
    StreamSession,
    # Gamification
    Achievement,
    UserAchievement,
    DonationAlert,
    # Support
    # Security
    SecurityLog,
    SystemLog,
    # Widgets
    ChatBoxSettings,
)

# Re-export the datetime helper for compatibility.
from core.datetime_utils import utcnow_naive

__all__ = [
    # Base
    "Base",
    "engine",
    "SessionLocal",
    "get_db",
    "db_session",
    "init_db",
    "DATABASE_URL",
    "IS_POSTGRESQL",
    # User
    "User",
    "UserSettings",
    "UserSession",
    "UserToken",
    "AdminUser",
    # TTS
    "TTSUserSettings",
    "TTSBlockedUser",
    "FilteredWord",
    "LocalTTSEndpoint",
    "AudioSettings",
    "UserVoiceSettings",
    "Worker",
    "WorkerPairingToken",
    "TTSJob",
    "TTSJobAttempt",
    # YouTube
    "YouTubeQueue",
    # Points
    "ChannelPoints",
    "ChannelReward",
    "PointsTransaction",
    "RewardQueue",
    # Commands
    "BotCommand",
    "CommandInvocation",
    # Moderation
    "BlockedBot",
    "BlockedChannel",
    "WhitelistedChannel",
    # Analytics
    "PsychologyAnalysis",
    "ChatMessage",
    "UserProgression",
    # Drops
    "DropsType",
    "DropsQuality",
    "DropsConfig",
    "DropsReward",
    "UserStreak",
    "DropsHistory",
    "MemeAlertsGrantHistory",
    "MythicalDropsSession",
    "PendingStreakChest",
    "StreamSession",
    # Gamification
    "Achievement",
    "UserAchievement",
    "DonationAlert",
    # Support
    # Security
    "SecurityLog",
    "SystemLog",
    # Widgets
    "ChatBoxSettings",
    # Utils
    "utcnow_naive",
]
