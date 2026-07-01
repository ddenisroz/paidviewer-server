"""Database model exports.

Models are split by domain for maintainability. This module re-exports the active
model set for compatibility with existing imports.
"""

# Base and infrastructure.
from models.base import DATABASE_URL, IS_POSTGRESQL, Base, SessionLocal, db_session, engine, init_db

# Import get_db from dependencies to avoid circular imports and keep a single source of truth.
from core.dependencies import get_db

# Users and sessions.
from models.user import AdminUser, User, UserSession, UserSettings, UserToken

# Bot tokens.
from models.bot_token import BotToken

# TTS settings.
from models.tts import AudioSettings, FilteredWord, LocalTTSEndpoint, TTSBlockedUser, TTSUserSettings, UserVoiceSettings
from models.worker import TTSJob, TTSJobAttempt, Worker, WorkerPairingToken

# YouTube queue.
from models.youtube import YouTubeQueue

# Channel points.
from models.points import ChannelPoints, ChannelReward, PointsTransaction, RewardQueue

# Bot commands.
from models.commands import BotCommand, CommandInvocation

# Moderation.
from models.moderation import BlockedBot, BlockedChannel, WhitelistedChannel

# Analytics and chat.
from models.analytics import ChatMessage, PsychologyAnalysis, UserProgression

# Drops system.
from models.drops import (
    DropsConfig,
    DropsHistory,
    DropsQuality,
    DropsReward,
    DropsType,
    MemeAlertsGrantHistory,
    MythicalDropsSession,
    PendingStreakChest,
    StreamSession,
    UserStreak,
)

# Gamification.
from models.gamification import Achievement, DonationAlert, UserAchievement

# Security and logs.
from models.security import SecurityLog, SystemLog

# Widgets.
from models.widgets import ChatBoxSettings

__all__ = [
    "Base",
    "engine",
    "SessionLocal",
    "get_db",
    "db_session",
    "init_db",
    "DATABASE_URL",
    "IS_POSTGRESQL",
    "User",
    "UserSettings",
    "UserSession",
    "UserToken",
    "AdminUser",
    "BotToken",
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
    "YouTubeQueue",
    "ChannelPoints",
    "ChannelReward",
    "PointsTransaction",
    "RewardQueue",
    "BotCommand",
    "CommandInvocation",
    "BlockedBot",
    "BlockedChannel",
    "WhitelistedChannel",
    "PsychologyAnalysis",
    "ChatMessage",
    "UserProgression",
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
    "Achievement",
    "UserAchievement",
    "DonationAlert",
    "SecurityLog",
    "SystemLog",
    "ChatBoxSettings",
]
