"""Legacy validation helpers for generic text, URL, and file checks."""

import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger("bot_service")


class ValidationError(Exception):
    """Raised when a validation check fails."""


class InputValidator:
    """Validate and sanitize common user-provided values."""

    USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{2,30}$")
    EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
    CHANNEL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{2,50}$")
    COMMAND_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{2,20}$")

    XSS_DANGEROUS_CHARS = ["<", ">", "&", '"', "'", "\\", "/", ";", "|", "`", "\n", "\r", "\t"]

    SQL_INJECTION_PATTERNS = [
        r"('\s*(or|and)\s*')",
        r"(;\s*drop\s+table)",
        r"(;\s*delete\s+from)",
        r"(union\s+select)",
        r"(exec\s*\()",
        r"(script>)",
    ]

    @staticmethod
    def sanitize_text(text: str, max_length: int = 500, allow_multiline: bool = False) -> str:
        """Strip dangerous characters and reject suspicious SQL-like input."""

        if not text:
            raise ValidationError("Text cannot be empty")

        text = text.strip()
        if len(text) > max_length:
            raise ValidationError(f"Text too long: {len(text)} > {max_length}")

        for char in InputValidator.XSS_DANGEROUS_CHARS:
            if not allow_multiline and char in ["\n", "\r", "\t"]:
                text = text.replace(char, " ")
            elif char not in ["\n", "\r", "\t"]:
                text = text.replace(char, "")

        for pattern in InputValidator.SQL_INJECTION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                raise ValidationError("Potentially dangerous SQL pattern detected")

        return text.strip()

    @staticmethod
    def validate_username(username: str) -> bool:
        """Validate a generic username."""

        if not username:
            raise ValidationError("Username cannot be empty")
        if not InputValidator.USERNAME_PATTERN.match(username):
            raise ValidationError("Invalid username format. Use only letters, numbers, _ and -")
        return True

    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate an email address."""

        if not email:
            raise ValidationError("Email cannot be empty")
        if not InputValidator.EMAIL_PATTERN.match(email):
            raise ValidationError("Invalid email format")
        return True

    @staticmethod
    def validate_channel_name(channel_name: str) -> bool:
        """Validate a stream or chat channel name."""

        if not channel_name:
            raise ValidationError("Channel name cannot be empty")
        if not InputValidator.CHANNEL_NAME_PATTERN.match(channel_name):
            raise ValidationError("Invalid channel name format")
        return True

    @staticmethod
    def validate_command_name(command_name: str) -> bool:
        """Validate a bot command name."""

        if not command_name:
            raise ValidationError("Command name cannot be empty")
        if not InputValidator.COMMAND_NAME_PATTERN.match(command_name):
            raise ValidationError("Invalid command name format. Use only letters, numbers, _ and -")

        reserved_words = ["admin", "mod", "owner", "system", "bot", "api"]
        if command_name.lower() in reserved_words:
            raise ValidationError(f"'{command_name}' is a reserved word")

        return True

    @staticmethod
    def validate_url(url: str, allowed_domains: Optional[List[str]] = None) -> bool:
        """Validate a URL and optionally restrict it to an allowed domain list."""

        if not url:
            raise ValidationError("URL cannot be empty")

        try:
            parsed = urlparse(url)

            if parsed.scheme not in ["http", "https"]:
                raise ValidationError("URL must use http or https scheme")
            if not parsed.netloc:
                raise ValidationError("URL must have a valid domain")

            if allowed_domains:
                domain = parsed.netloc.lower()
                if domain.startswith("www."):
                    domain = domain[4:]

                allowed = False
                for allowed_domain in allowed_domains:
                    if domain == allowed_domain or domain.endswith(f".{allowed_domain}"):
                        allowed = True
                        break

                if not allowed:
                    raise ValidationError(f"Domain not allowed. Allowed: {', '.join(allowed_domains)}")

            return True

        except Exception as exc:
            if isinstance(exc, ValidationError):
                raise
            raise ValidationError(f"Invalid URL: {exc}")

    @staticmethod
    def validate_youtube_url(url: str) -> Dict[str, Any]:
        """Validate a YouTube URL and extract its video ID."""

        youtube_domains = ["youtube.com", "youtu.be", "m.youtube.com"]

        try:
            InputValidator.validate_url(url, youtube_domains)
            parsed = urlparse(url)

            video_id = None
            if "youtu.be" in parsed.netloc:
                video_id = parsed.path.lstrip("/")
            elif "youtube.com" in parsed.netloc:
                query_params = parse_qs(parsed.query)
                video_id = query_params.get("v", [None])[0]

            if not video_id:
                raise ValidationError("Could not extract video ID from YouTube URL")
            if not re.match(r"^[a-zA-Z0-9_-]{11}$", video_id):
                raise ValidationError("Invalid YouTube video ID format")

            return {
                "valid": True,
                "video_id": video_id,
                "url": url,
                "platform": "youtube",
            }

        except Exception as exc:
            if isinstance(exc, ValidationError):
                raise
            raise ValidationError(f"Invalid YouTube URL: {exc}")

    @staticmethod
    def validate_number_range(
        value: Any,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        field_name: str = "Value",
    ) -> float:
        """Validate that a numeric value falls into the configured range."""

        try:
            num = float(value)
        except (TypeError, ValueError):
            raise ValidationError(f"{field_name} must be a number")

        if min_value is not None and num < min_value:
            raise ValidationError(f"{field_name} must be >= {min_value}")
        if max_value is not None and num > max_value:
            raise ValidationError(f"{field_name} must be <= {max_value}")

        return num

    @staticmethod
    def validate_integer(value: Any, field_name: str = "Value") -> int:
        """Validate that a value can be converted to an integer."""

        try:
            return int(value)
        except (TypeError, ValueError):
            raise ValidationError(f"{field_name} must be an integer")


class FileValidator:
    """Validate uploaded audio files against simple size and MIME rules."""

    ALLOWED_AUDIO_MIME_TYPES = [
        "audio/wav",
        "audio/x-wav",
        "audio/wave",
        "audio/mp3",
        "audio/mpeg",
        "audio/ogg",
        "audio/flac",
    ]
    ALLOWED_AUDIO_EXTENSIONS = [".wav", ".mp3", ".ogg", ".flac"]
    MAX_AUDIO_FILE_SIZE = 50 * 1024 * 1024

    @staticmethod
    def validate_audio_file(filename: str, content_type: str, file_size: int) -> bool:
        """Validate a legacy audio upload payload."""

        if file_size > FileValidator.MAX_AUDIO_FILE_SIZE:
            raise ValidationError(
                f"File too large: {file_size} bytes. Max: {FileValidator.MAX_AUDIO_FILE_SIZE} bytes"
            )

        file_ext = None
        for ext in FileValidator.ALLOWED_AUDIO_EXTENSIONS:
            if filename.lower().endswith(ext):
                file_ext = ext
                break

        if not file_ext:
            raise ValidationError(
                f"Invalid file extension. Allowed: {', '.join(FileValidator.ALLOWED_AUDIO_EXTENSIONS)}"
            )

        if content_type not in FileValidator.ALLOWED_AUDIO_MIME_TYPES:
            raise ValidationError(
                f"Invalid MIME type: {content_type}. Allowed: {', '.join(FileValidator.ALLOWED_AUDIO_MIME_TYPES)}"
            )

        return True
