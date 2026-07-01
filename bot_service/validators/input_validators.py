"""Input validators and sanitizers for the API layer."""

import html
import re
from typing import Any, Dict, Optional

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

CYRILLIC_RANGE = "\\u0400-\\u04FF"
ALPHANUMERIC_WITH_CYRILLIC = rf"^[a-zA-Z0-9{CYRILLIC_RANGE}\s\-_]+$"
USERNAME_WITH_CYRILLIC = rf"^[a-zA-Z0-9{CYRILLIC_RANGE}_\-]+$"
VOICE_NAME_WITH_CYRILLIC = rf"[^a-zA-Z{CYRILLIC_RANGE}0-9\s_-]"


class BaseValidator(BaseModel):
    """Base validator with common safety rules."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class VoiceUploadValidator(BaseValidator):
    """Validator for uploaded voice files."""

    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    file_size: int = Field(..., gt=0, le=10 * 1024 * 1024)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not re.match(ALPHANUMERIC_WITH_CYRILLIC, value):
            raise ValueError("Name contains invalid characters")
        return value.strip()

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: Optional[str]) -> Optional[str]:
        if value is not None:
            value = re.sub(r"[<>\"']", "", value)
        return value


class TTSMessageValidator(BaseValidator):
    """Validator for TTS synthesis requests."""

    text: str = Field(..., min_length=1, max_length=500)
    voice_id: Optional[int] = Field(None, gt=0)
    speed: Optional[float] = Field(1.0, ge=0.5, le=2.0)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        value = re.sub(r"[<>\"']", "", value)
        if len(value) > 500:
            raise ValueError("Text too long")
        return value.strip()


class UserSettingsValidator(BaseValidator):
    """Validator for user settings updates."""

    website_volume: int = Field(50, ge=0, le=100)
    obs_volume: int = Field(50, ge=0, le=100)
    enable_7tv: bool = Field(True)
    enable_twitch: bool = Field(True)
    enable_lexicon_filter: bool = Field(True)
    enable_custom_lexicon: bool = Field(False)


class AdminUserValidator(BaseValidator):
    """Validator for admin user creation payloads."""

    platform: str = Field(..., pattern=r"^(twitch|vk)$")
    platform_user_id: str = Field(..., min_length=1, max_length=100)
    username: Optional[str] = Field(None, max_length=100)
    permissions: Optional[Dict[str, Any]] = Field(None)

    @field_validator("platform_user_id")
    @classmethod
    def validate_platform_user_id(cls, value: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_\-]+$", value):
            raise ValueError("Invalid platform user ID format")
        return value


class FilteredWordValidator(BaseValidator):
    """Validator for filtered words."""

    word: str = Field(..., min_length=1, max_length=50)
    is_regex: bool = Field(False)

    @field_validator("word")
    @classmethod
    def validate_word(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Word cannot be empty")
        return value.strip().lower()


def validate_file_upload(file: Any, max_size: int = 10 * 1024 * 1024) -> None:
    """Validate a basic uploaded audio file object."""

    if not file:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No file provided")

    if file.size > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size: {max_size // (1024 * 1024)}MB",
        )

    allowed_extensions = [".wav", ".mp3", ".ogg", ".m4a"]
    file_extension = file.filename.lower().split(".")[-1] if "." in file.filename else ""

    if f".{file_extension}" not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed: {', '.join(allowed_extensions)}",
        )


def sanitize_input(text: str, max_length: int = 1000, allow_special: bool = False) -> str:
    """Sanitize user input against XSS and unsafe raw-SQL usage."""

    if not text:
        return ""

    text = html.escape(text)

    if not allow_special:
        text = re.sub(r"[<>\"';\\`]", "", text)

    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", text)

    if len(text) > max_length:
        text = text[:max_length]

    return text.strip()


def sanitize_stream_title(title: str) -> str:
    """Sanitize a stream title for safe storage and display."""

    if not title:
        return ""

    title = re.sub(r"<[^>]*>", "", title)
    title = re.sub(r"javascript:", "", title, flags=re.IGNORECASE)
    title = re.sub(r"on\w+\s*=", "", title, flags=re.IGNORECASE)
    title = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", title)

    if len(title) > 140:
        title = title[:140]

    return title.strip()


def sanitize_tts_message(message: str) -> str:
    """Sanitize a TTS message before synthesis."""

    if not message:
        return ""

    message = re.sub(r"<[^>]*>", "", message)
    message = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", message)

    if len(message) > 500:
        message = message[:500]

    return message.strip()


def sanitize_voice_name(name: str) -> str:
    """Sanitize a voice display name."""

    if not name:
        return ""

    name = re.sub(VOICE_NAME_WITH_CYRILLIC, "", name)

    if len(name) > 50:
        name = name[:50]

    return name.strip()


def sanitize_file_name(filename: str) -> str:
    """Sanitize a filename for safe storage."""

    if not filename:
        return ""

    filename = filename.replace("..", "")
    filename = re.sub(r"[/\\]", "", filename)
    filename = re.sub(r"[<>:\"|?*\x00-\x1f]", "", filename)

    if len(filename) > 255:
        filename = filename[:255]

    return filename.strip()


def sanitize_sql_string(text: str) -> str:
    """Sanitize a string before using it in raw SQL fragments."""

    if not text:
        return ""

    text = text.replace("'", "''")
    text = re.sub(r"(-{2}|/\*|\*/)|(;)", "", text)

    if len(text) > 1000:
        text = text[:1000]

    return text.strip()


def validate_username(username: str) -> str:
    """Validate a platform username."""

    if not username or len(username) < 1 or len(username) > 100:
        raise ValueError("Username must be between 1 and 100 characters")

    if not re.match(USERNAME_WITH_CYRILLIC, username):
        raise ValueError("Username contains invalid characters")

    return username.strip()


def validate_email(email: str) -> str:
    """Validate an email address."""

    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
        raise ValueError("Invalid email format")

    return email.lower().strip()


def validate_url(url: str) -> str:
    """Validate a URL string."""

    if not url:
        raise ValueError("URL cannot be empty")

    if not url.startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://")

    if len(url) > 2048:
        raise ValueError("URL is too long")

    return url.strip()


def validate_command_name(name: str) -> str:
    """Validate a command name."""

    if not name or len(name) < 1 or len(name) > 50:
        raise ValueError("Command name must be between 1 and 50 characters")

    if not re.match(r"^[a-zA-Z0-9_]+$", name):
        raise ValueError("Command name contains invalid characters")

    return name.lower().strip()


def validate_json_key(key: str) -> str:
    """Validate a JSON object key."""

    if not key or len(key) < 1 or len(key) > 100:
        raise ValueError("JSON key must be between 1 and 100 characters")

    if not re.match(r"^[a-zA-Z0-9_\-]+$", key):
        raise ValueError("JSON key contains invalid characters")

    return key.strip()


def validate_pagination(page: int = 1, limit: int = 20) -> tuple[int, int]:
    """Normalize pagination parameters."""

    if page < 1:
        page = 1
    if limit < 1 or limit > 100:
        limit = 20

    return page, limit
