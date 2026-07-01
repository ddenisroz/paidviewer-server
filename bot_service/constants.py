"""
Core constants used across bot_service.
Only static values live here; dynamic URLs and environment values come from core.config.settings.
"""

from core.config import settings
from enum import StrEnum


# URL constants
DEFAULT_FRONTEND_URL = settings.frontend_url
DEFAULT_BACKEND_URL = settings.backend_url

# OAuth redirects
OAUTH_REDIRECT_URLS = {
    "twitch": f"{DEFAULT_BACKEND_URL}/auth/twitch/callback",
    "vk": f"{DEFAULT_BACKEND_URL}/auth/vk/callback",
}

# Frontend redirects
FRONTEND_REDIRECTS = {
    "dashboard": f"{DEFAULT_FRONTEND_URL}/dashboard",
    "settings": f"{DEFAULT_FRONTEND_URL}/dashboard/settings",
    "login": f"{DEFAULT_FRONTEND_URL}/login",
}

# Time constants (seconds/minutes)
SESSION_MAX_AGE_SECONDS = 315360000  # 10 years
VERIFICATION_TIMEOUT_SECONDS = 60
MESSAGE_CHECK_INTERVAL = 5
BOT_CONNECTION_WAIT = 2
STREAM_ONLINE_THRESHOLD_MINUTES = 5

# TTS reconnect timeout
TTS_RECONNECT_TIMEOUT_SECONDS = 60


class AuthType(StrEnum):
    FULL = "full"


# HTTP_STATUS removed - use starlette.status instead


# TTS constants
TTS_DEFAULT_CFG_STRENGTH = 2.5
TTS_DEFAULT_VOLUME = 50.0
TTS_DEFAULT_SPEED_PRESET = "normal"
TTS_CROSS_FADE_DURATION = 0.15
TTS_SILENCE_DURATION_MS = 100
TTS_SWAY_SAMPLING_COEF = -1.0
TTS_MESSAGE_MAX_LENGTH = 500
TTS_MAX_RETRIES = 2
TTS_RETRY_DELAY = 0.5
TTS_HEALTH_CHECK_INTERVAL = 30

# YouTube constants
MAX_YOUTUBE_QUEUE_SIZE = 10

# Platforms
SUPPORTED_PLATFORMS = ["twitch", "vk"]
DEFAULT_ENABLED_PLATFORMS = []
ALL_SUPPORTED_PLATFORMS = ["twitch", "vk", "youtube"]

PLATFORM_NAMES = {
    "twitch": "Twitch",
    "vk": "VK Live",
    "youtube": "YouTube",
}


class Platform(StrEnum):
    TWITCH = "twitch"
    VK = "vk"
    YOUTUBE = "youtube"


class UserRole(StrEnum):
    ADMIN = "admin"
    USER = "user"


# OAuth scopes
OAUTH_SCOPES = {
    "twitch": "user:read:email channel:read:stream_key channel:manage:broadcast channel:manage:redemptions",
    "vk": "channel:stream:settings,channel:points:rewards,channel:points:rewards:demands,chat:message:send",
}

# Logging
DEFAULT_LOG_LEVEL = "DEBUG"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# DB defaults
DEFAULT_BLOCKED_BOTS = ["StreamElements", "Nightbot", "Streamlabs", "Moobot", "TwirApp"]


class ApiResponse(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    AUTHENTICATION_REQUIRED = "authentication_required"
    INVALID_REQUEST = "invalid_request"
    RATE_LIMITED = "rate_limited"


class ErrorMessages(StrEnum):
    OAUTH_FAILED = "OAuth authorization failed"
    NO_AUTH_CODE = "No authorization code received"
    INVALID_CREDENTIALS = "Invalid credentials"
    TOKEN_EXPIRED = "Token has expired"

    USER_NOT_FOUND = "User not found"
    USER_CREATION_FAILED = "Could not create user account"

    BOT_NOT_RUNNING = "Bot not running"
    BOT_CONNECTION_FAILED = "Failed to connect bot to channel"
    BOT_DISCONNECTION_FAILED = "Failed to disconnect bot from channel"

    CHANNEL_BLOCKED = "Channel is blocked"
    CHANNEL_NOT_WHITELISTED = "Channel not whitelisted for TTS"

    TTS_NOT_ENABLED = "TTS not enabled for this channel"
    TTS_MESSAGE_TOO_LONG = f"Message too long (max {TTS_MESSAGE_MAX_LENGTH} characters)"

    INTERNAL_ERROR = "Internal server error"
    INVALID_REQUEST = "Invalid request"
    MISSING_PARAMETER = "Missing required parameter"


class SuccessMessages(StrEnum):
    USER_CREATED = "User account created successfully"
    INTEGRATION_ENABLED = "Integration enabled successfully"
    INTEGRATION_DISABLED = "Integration disabled successfully"
    BOT_CONNECTED = "Bot connected successfully"
    BOT_DISCONNECTED = "Bot disconnected successfully"
    TTS_ENABLED = "TTS enabled"
    TTS_DISABLED = "TTS disabled"


class EnvVars(StrEnum):
    DATABASE_URL = "DATABASE_URL"

    SECRET_KEY = "SECRET_KEY"
    ALGORITHM = "ALGORITHM"

    TWITCH_CLIENT_ID = "TWITCH_CLIENT_ID"
    TWITCH_CLIENT_SECRET = "TWITCH_CLIENT_SECRET"

    VK_CLIENT_ID = "VK_CLIENT_ID"
    VK_CLIENT_SECRET = "VK_CLIENT_SECRET"
    VK_REDIRECT_URI = "VK_REDIRECT_URI"
    VK_AUTH_BASE_URL = "VK_AUTH_BASE_URL"

    F5_TTS_SERVICE_URL = "F5_TTS_SERVICE_URL"

    ADMIN_USERS = "ADMIN_USERS"

    LOG_LEVEL = "LOG_LEVEL"


class WSEvents(StrEnum):
    USER_CONNECTED = "user_connected"
    USER_DISCONNECTED = "user_disconnected"
    MESSAGE_RECEIVED = "message_received"
    TTS_REQUEST = "tts_request"
    INTEGRATION_UPDATE = "integration_update"
    BOT_STATUS_CHANGE = "bot_status_change"


class CacheKeys(StrEnum):
    TWITCH_CATEGORIES = "twitch:categories"
    TWITCH_STREAMS = "twitch:streams"
    YOUTUBE_VIDEOS = "youtube:videos"
    USER_SESSIONS = "user:sessions"
    BOT_STATUS = "bot:status"


class ValidationRules:
    USERNAME_MIN_LENGTH = 3
    USERNAME_MAX_LENGTH = 25
    PASSWORD_MIN_LENGTH = 8
    CHANNEL_NAME_MIN_LENGTH = 3
    CHANNEL_NAME_MAX_LENGTH = 25

    USERNAME_PATTERN = r"^[a-zA-Z0-9_]{3,25}$"
    CHANNEL_NAME_PATTERN = r"^[a-zA-Z0-9_]{3,25}$"


class RateLimit:
    REQUESTS_PER_MINUTE = 60
    REQUESTS_PER_HOUR = 1000
    AUTH_ATTEMPTS_PER_HOUR = 5
    TTS_REQUESTS_PER_MINUTE = 10
