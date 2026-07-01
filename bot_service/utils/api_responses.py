"""Standard API response helpers for consistent JSON payloads."""

from typing import Any, Dict, Optional

from fastapi import status
from fastapi.responses import JSONResponse


class StandardResponse:
    """Create standardized API responses for success and error cases."""

    @staticmethod
    def success(
        data: Optional[Any] = None,
        message: Optional[str] = None,
        status_code: int = status.HTTP_200_OK,
    ) -> JSONResponse:
        """Return a successful JSON response."""

        content: Dict[str, Any] = {"success": True}
        if data is not None:
            content["data"] = data
        if message:
            content["message"] = message
        return JSONResponse(status_code=status_code, content=content)

    @staticmethod
    def error(
        message: str,
        code: str = "UNKNOWN_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None,
    ) -> JSONResponse:
        """Return a standardized error response."""

        error_obj: Dict[str, Any] = {"code": code, "message": message}
        if details:
            error_obj["details"] = details

        return JSONResponse(
            status_code=status_code,
            content={"success": False, "error": error_obj},
        )

    @staticmethod
    def created(data: Any, message: Optional[str] = None, resource_id: Optional[Any] = None) -> JSONResponse:
        """Return a 201 response for a newly created resource."""

        response_data = data
        if resource_id is not None and isinstance(data, dict):
            response_data = {**data, "id": resource_id}

        return StandardResponse.success(
            data=response_data,
            message=message or "Resource created successfully",
            status_code=status.HTTP_201_CREATED,
        )

    @staticmethod
    def no_content(message: Optional[str] = None) -> JSONResponse:
        """Return a 204 response for delete-like operations."""

        content: Dict[str, Any] = {"success": True}
        if message:
            content["message"] = message

        return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content=content)

    @staticmethod
    def bad_request(message: str, code: str = "BAD_REQUEST", details: Optional[Dict[str, Any]] = None) -> JSONResponse:
        """Return a 400 bad request response."""

        return StandardResponse.error(
            message=message,
            code=code,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
        )

    @staticmethod
    def unauthorized(message: str = "Authentication required", code: str = "UNAUTHORIZED") -> JSONResponse:
        """Return a 401 unauthorized response."""

        return StandardResponse.error(
            message=message,
            code=code,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    @staticmethod
    def forbidden(message: str = "Access denied", code: str = "FORBIDDEN") -> JSONResponse:
        """Return a 403 forbidden response."""

        return StandardResponse.error(
            message=message,
            code=code,
            status_code=status.HTTP_403_FORBIDDEN,
        )

    @staticmethod
    def not_found(
        message: str = "Resource not found",
        code: str = "NOT_FOUND",
        resource_type: Optional[str] = None,
    ) -> JSONResponse:
        """Return a 404 not found response."""

        details = {"resource_type": resource_type} if resource_type else None
        return StandardResponse.error(
            message=message,
            code=code,
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
        )

    @staticmethod
    def conflict(message: str, code: str = "CONFLICT", details: Optional[Dict[str, Any]] = None) -> JSONResponse:
        """Return a 409 conflict response."""

        return StandardResponse.error(
            message=message,
            code=code,
            status_code=status.HTTP_409_CONFLICT,
            details=details,
        )

    @staticmethod
    def too_many_requests(
        message: str = "Too many requests",
        code: str = "RATE_LIMIT_EXCEEDED",
        retry_after: Optional[int] = None,
    ) -> JSONResponse:
        """Return a 429 rate-limit response."""

        details = {"retry_after_seconds": retry_after} if retry_after else None
        response = StandardResponse.error(
            message=message,
            code=code,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details=details,
        )

        if retry_after:
            response.headers["Retry-After"] = str(retry_after)

        return response


class ErrorCodes:
    """Centralized API error code constants."""

    UNAUTHORIZED = "UNAUTHORIZED"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"

    TTS_NOT_AVAILABLE = "TTS_NOT_AVAILABLE"
    TTS_NOT_WHITELISTED = "TTS_NOT_WHITELISTED"
    TTS_ENABLE_FAILED = "TTS_ENABLE_FAILED"
    TTS_VOICE_NOT_FOUND = "TTS_VOICE_NOT_FOUND"

    COMMAND_NOT_FOUND = "COMMAND_NOT_FOUND"
    COMMAND_LIMIT_EXCEEDED = "COMMAND_LIMIT_EXCEEDED"
    INVALID_COMMAND_NAME = "INVALID_COMMAND_NAME"

    BAD_REQUEST = "BAD_REQUEST"
    NOT_FOUND = "NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
