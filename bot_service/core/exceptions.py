# core/exceptions.py
"""Custom exceptions for application business logic."""
from typing import Any, Optional


class AppException(Exception):
    """Base application exception."""
    
    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"
    
    def __init__(
        self, 
        message: str, 
        details: Optional[dict[str, Any]] = None,
        cause: Optional[Exception] = None
    ):
        self.message = message
        self.details = details or {}
        self.cause = cause
        super().__init__(message)
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize the exception for JSON responses."""
        result = {
            "error_code": self.error_code,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        return result


# === Authentication & Authorization ===

class AuthenticationError(AppException):
    """Authentication error."""
    status_code = 401
    error_code = "AUTHENTICATION_ERROR"


class AuthorizationError(AppException):
    """Authorization error due to insufficient permissions."""
    status_code = 403
    error_code = "AUTHORIZATION_ERROR"


class TokenExpiredError(AuthenticationError):
    """Token expired."""
    error_code = "TOKEN_EXPIRED"


class InvalidTokenError(AuthenticationError):
    """Invalid token."""
    error_code = "INVALID_TOKEN"


class SessionExpiredError(AuthenticationError):
    """Session expired."""
    error_code = "SESSION_EXPIRED"


# === Resource Errors ===

class NotFoundError(AppException):
    """Resource not found."""
    status_code = 404
    error_code = "NOT_FOUND"

    def __init__(self, resource: str, identifier: Any, **kwargs):
        message = f"{resource} not found: {identifier}"
        super().__init__(message, details={"resource": resource, "id": identifier}, **kwargs)


class AlreadyExistsError(AppException):
    """Resource already exists."""
    status_code = 409
    error_code = "ALREADY_EXISTS"

    def __init__(self, resource: str, identifier: Any, **kwargs):
        message = f"{resource} already exists: {identifier}"
        super().__init__(message, details={"resource": resource, "id": identifier}, **kwargs)


# === Validation Errors ===

class ValidationError(AppException):
    """Validation error."""
    status_code = 422
    error_code = "VALIDATION_ERROR"


class InvalidInputError(ValidationError):
    """Invalid input data."""
    error_code = "INVALID_INPUT"

    def __init__(self, field: str, reason: str, **kwargs):
        message = f"Invalid value for field '{field}': {reason}"
        super().__init__(message, details={"field": field, "reason": reason}, **kwargs)


# === Platform Errors ===

class PlatformError(AppException):
    """Platform error (Twitch, VK, etc.)."""
    status_code = 502
    error_code = "PLATFORM_ERROR"
    
    def __init__(self, platform: str, message: str, **kwargs):
        super().__init__(f"[{platform.upper()}] {message}", details={"platform": platform}, **kwargs)


class PlatformConnectionError(PlatformError):
    """Platform connection error."""
    error_code = "PLATFORM_CONNECTION_ERROR"


class PlatformAPIError(PlatformError):
    """Platform API error."""
    error_code = "PLATFORM_API_ERROR"


# === Bot Errors ===

class BotError(AppException):
    """Bot error."""
    status_code = 500
    error_code = "BOT_ERROR"


class BotNotConnectedError(BotError):
    """Bot is not connected."""
    status_code = 503
    error_code = "BOT_NOT_CONNECTED"

    def __init__(self, platform: str, **kwargs):
        message = f"{platform} bot is not connected"
        super().__init__(message, details={"platform": platform}, **kwargs)


class BotAlreadyConnectedError(BotError):
    """Bot is already connected."""
    status_code = 409
    error_code = "BOT_ALREADY_CONNECTED"


# === TTS Errors ===

class TTSError(AppException):
    """TTS error."""
    status_code = 500
    error_code = "TTS_ERROR"


class TTSServiceUnavailableError(TTSError):
    """TTS service is unavailable."""
    status_code = 503
    error_code = "TTS_SERVICE_UNAVAILABLE"


class TTSVoiceNotFoundError(TTSError):
    """TTS voice not found."""
    status_code = 404
    error_code = "TTS_VOICE_NOT_FOUND"


# === Database Errors ===

class DatabaseError(AppException):
    """Database error."""
    status_code = 500
    error_code = "DATABASE_ERROR"


class DatabaseConnectionError(DatabaseError):
    """Database connection error."""
    error_code = "DATABASE_CONNECTION_ERROR"


# === Rate Limiting ===

class RateLimitError(AppException):
    """Rate limit exceeded."""
    status_code = 429
    error_code = "RATE_LIMIT_EXCEEDED"

    def __init__(self, retry_after: Optional[int] = None, **kwargs):
        message = "Rate limit exceeded"
        details = {}
        if retry_after:
            details["retry_after"] = retry_after
            message += f", retry in {retry_after}s"
        super().__init__(message, details=details, **kwargs)


# === External Service Errors ===

class ExternalServiceError(AppException):
    """External service error."""
    status_code = 502
    error_code = "EXTERNAL_SERVICE_ERROR"
    
    def __init__(self, service: str, message: str, **kwargs):
        super().__init__(f"[{service}] {message}", details={"service": service}, **kwargs)
