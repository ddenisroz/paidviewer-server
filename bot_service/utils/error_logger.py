"""Enhanced structured error logging with sensitive-data redaction."""

import logging
import re
from typing import Any, Dict, Optional

from core.datetime_utils import utcnow_naive

logger = logging.getLogger(__name__)


class SensitiveDataFilter(logging.Filter):
    """Redact sensitive values from log records."""

    SENSITIVE_PATTERNS = [
        (r"(token|access_token|refresh_token|api_key|secret|password|pwd)[\s:=]+[\"']?([^\"'\s]+)[\"']?", r"\1=***REDACTED***"),
        (r"Bearer\s+([A-Za-z0-9\-._~+/]+=*)", r"Bearer ***REDACTED***"),
        (r"eyJ[A-Za-z0-9\-._~+/]+=*\.eyJ[A-Za-z0-9\-._~+/]+=*\.[A-Za-z0-9\-._~+/]+=*", r"***JWT_REDACTED***"),
        (r"([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", r"\1@***"),
        (r"\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}", r"***PHONE***"),
        (r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.)\d{1,3}", r"\1***"),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact sensitive content from `msg` and `args`."""

        if hasattr(record, "msg"):
            record.msg = self.redact_sensitive_data(str(record.msg))

        if hasattr(record, "args") and record.args:
            if isinstance(record.args, dict):
                record.args = {key: self.redact_sensitive_data(str(value)) for key, value in record.args.items()}
            elif isinstance(record.args, (list, tuple)):
                record.args = tuple(self.redact_sensitive_data(str(arg)) for arg in record.args)

        return True

    def redact_sensitive_data(self, text: str) -> str:
        """Replace sensitive fragments with redacted placeholders."""

        for pattern, replacement in self.SENSITIVE_PATTERNS:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text


class StructuredErrorLogger:
    """Structured error logger with contextual metadata."""

    def __init__(self, logger_name: str = "bot_service.errors"):
        self.logger = logging.getLogger(logger_name)
        self.logger.addFilter(SensitiveDataFilter())

    def log_error(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
        endpoint: Optional[str] = None,
        severity: str = "ERROR",
    ):
        """Log an exception with structured context."""

        error_data = {
            "timestamp": utcnow_naive().isoformat(),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "user_id": user_id,
            "endpoint": endpoint,
            "context": context or {},
        }

        log_level = getattr(logging, severity.upper(), logging.ERROR)
        self.logger.log(log_level, f"Error occurred: {error_data['error_type']}", extra=error_data, exc_info=True)

    def log_validation_error(self, errors: list, endpoint: str, user_id: Optional[int] = None):
        """Log validation errors."""

        error_data = {
            "timestamp": utcnow_naive().isoformat(),
            "error_type": "ValidationError",
            "endpoint": endpoint,
            "user_id": user_id,
            "validation_errors": errors,
        }
        self.logger.warning(f"Validation error in {endpoint}", extra=error_data)

    def log_api_error(
        self,
        status_code: int,
        endpoint: str,
        method: str,
        error_message: str,
        user_id: Optional[int] = None,
        response_time: Optional[float] = None,
    ):
        """Log API error responses."""

        error_data = {
            "timestamp": utcnow_naive().isoformat(),
            "error_type": "APIError",
            "status_code": status_code,
            "endpoint": endpoint,
            "method": method,
            "error_message": error_message,
            "user_id": user_id,
            "response_time_ms": response_time,
        }

        if status_code >= 500:
            log_level = logging.ERROR
        elif status_code >= 400:
            log_level = logging.WARNING
        else:
            log_level = logging.INFO

        self.logger.log(log_level, f"API {status_code} {method} {endpoint}", extra=error_data)

    def log_database_error(self, error: Exception, operation: str, table: Optional[str] = None, user_id: Optional[int] = None):
        """Log a database error."""

        error_data = {
            "timestamp": utcnow_naive().isoformat(),
            "error_type": "DatabaseError",
            "operation": operation,
            "table": table,
            "error_message": str(error),
            "user_id": user_id,
        }
        self.logger.error(f"Database error during {operation}", extra=error_data, exc_info=True)

    def log_external_api_error(
        self,
        service: str,
        endpoint: str,
        status_code: Optional[int],
        error_message: str,
        user_id: Optional[int] = None,
    ):
        """Log an external API error."""

        error_data = {
            "timestamp": utcnow_naive().isoformat(),
            "error_type": "ExternalAPIError",
            "service": service,
            "endpoint": endpoint,
            "status_code": status_code,
            "error_message": error_message,
            "user_id": user_id,
        }
        self.logger.error(f"External API error: {service} - {error_message}", extra=error_data)


error_logger = StructuredErrorLogger()


def log_error_with_context(error: Exception, context: Optional[Dict[str, Any]] = None, **kwargs):
    """Convenience helper for structured error logging."""

    error_logger.log_error(error, context=context, **kwargs)


def redact_sensitive_data(data: Any) -> Any:
    """Redact sensitive data from nested structures."""

    sensitive_filter = SensitiveDataFilter()

    if isinstance(data, dict):
        return {key: redact_sensitive_data(value) for key, value in data.items()}
    if isinstance(data, (list, tuple)):
        return [redact_sensitive_data(item) for item in data]
    if isinstance(data, str):
        return sensitive_filter.redact_sensitive_data(data)
    return data
