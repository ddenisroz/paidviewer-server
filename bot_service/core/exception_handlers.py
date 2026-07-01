"""
Centralized exception handlers for FastAPI.

Handles:
- AppException and derived business errors
- HTTPException
- RequestValidationError / ValidationError
- SQLAlchemyError
- any other unhandled exception
"""
import logging
from core.datetime_utils import utcnow_naive
from typing import Union

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError, HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from core.exceptions import AppException
from utils.error_logger import error_logger

logger = logging.getLogger(__name__)


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Global handler for all unhandled exceptions.

    Prevents application crashes and records the error details.
    """
    # Extract user context when available.
    user_id = getattr(request.state, "user_id", None)

    # Use structured logging.
    error_logger.log_error(
        exc,
        context={
            "method": request.method,
            "path": request.url.path,
            "query_params": dict(request.query_params),
            "client_host": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
            "content_type": request.headers.get("content-type"),
            # Add safe headers snapshot (excluding sensitive auth)
            "headers_snapshot": {
                k: v for k, v in request.headers.items() 
                if k.lower() not in ('authorization', 'cookie', 'x-api-key')
            }
        },
        user_id=user_id,
        endpoint=request.url.path,
        severity="CRITICAL",
    )

    # Do not expose internal details to clients.
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error",
            "timestamp": utcnow_naive().isoformat(),
        },
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Handler for FastAPI HTTPException.
    """
    user_id = getattr(request.state, "user_id", None)

    # Log unexpected HTTP errors only.
    if exc.status_code not in [401, 403, 404]:
        logger.warning(
            f"HTTP {exc.status_code} in {request.method} {request.url.path}: {exc.detail}",
            extra={
                "user_id": user_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": exc.status_code,
                "timestamp": utcnow_naive().isoformat(),
            },
        )

    # Preserve 503 details for actionable dependency/runtime availability messages.
    # Other 5xx responses stay sanitized.
    response_detail = exc.detail
    if exc.status_code >= 500 and exc.status_code != 503:
        response_detail = "Internal server error"

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": response_detail,
            "timestamp": utcnow_naive().isoformat(),
        },
    )


async def validation_exception_handler(
    request: Request, exc: Union[RequestValidationError, ValidationError]
) -> JSONResponse:
    """
    Handler for Pydantic validation errors.
    """
    user_id = getattr(request.state, "user_id", None)

    # Format validation errors.
    errors = []
    for error in exc.errors():
        field_path = " -> ".join(str(loc) for loc in error["loc"][1:])  # Skip 'body'
        errors.append({
            "field": field_path,
            "message": error["msg"],
            "type": error["type"],
        })

    # Use structured logging.
    error_logger.log_validation_error(
        errors=errors,
        endpoint=request.url.path,
        user_id=user_id,
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Validation error",
            "errors": errors,
            "timestamp": utcnow_naive().isoformat(),
        },
    )


async def database_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """
    Handler for database errors.
    """
    user_id = getattr(request.state, "user_id", None)

    # Use structured logging.
    error_logger.log_database_error(
        exc,
        operation=f"{request.method} {request.url.path}",
        user_id=user_id,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Database error",
            "timestamp": utcnow_naive().isoformat(),
        },
    )


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """
    Handler for AppException business errors.
    """
    user_id = getattr(request.state, "user_id", None)

    # Log 5xx errors with structured context.
    if exc.status_code >= 500:
        error_logger.log_error(
            exc,
            context={
                "method": request.method,
                "path": request.url.path,
                "error_code": exc.error_code,
                "details": exc.details,
            },
            user_id=user_id,
            endpoint=request.url.path,
            severity="ERROR",
        )
    else:
        logger.info(
            f"[{exc.error_code}] {request.method} {request.url.path}: {exc.message}",
            extra={
                "user_id": user_id,
                "error_code": exc.error_code,
                "status_code": exc.status_code,
            },
        )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            **exc.to_dict(),
            "timestamp": utcnow_naive().isoformat(),
        },
    )


def setup_exception_handlers(app):
    """
    Register exception handlers in the FastAPI application.
    """
    # Global handler for all unhandled exceptions.
    app.add_exception_handler(Exception, global_exception_handler)

    # Handler for HTTPException.
    app.add_exception_handler(HTTPException, http_exception_handler)

    # Handlers for validation errors.
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)

    # Handler for database errors.
    app.add_exception_handler(SQLAlchemyError, database_exception_handler)

    # Handler for business exceptions.
    app.add_exception_handler(AppException, app_exception_handler)

    logger.debug("Exception handlers registered")
