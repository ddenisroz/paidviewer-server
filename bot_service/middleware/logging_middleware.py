# bot_service/middleware/logging_middleware.py
"""
Logging Middleware for FastAPI

Automatically logs all HTTP requests and responses with:
- Request details (method, path, headers, body)
- Response details (status code, duration)
- User context (if authenticated)
- Error tracking
"""
import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from core.structured_logging import get_logger, bind_context, unbind_context
from core.sentry_config import add_breadcrumb, set_user_context

logger = get_logger(__name__)


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds structured logging to all requests.
    
    Features:
    - Automatic request/response logging
    - Request ID generation
    - User context binding
    - Performance tracking
    - Sentry breadcrumbs
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate request ID
        request_id = str(uuid.uuid4())
        
        # Bind request context
        bind_context(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        
        # Add Sentry breadcrumb
        add_breadcrumb(
            message=f"{request.method} {request.url.path}",
            category="http",
            level="info",
            data={
                "request_id": request_id,
                "method": request.method,
                "url": str(request.url),
            }
        )
        
        # Get user context if available
        user_id = None
        if hasattr(request.state, "user"):
            user_id = request.state.user.get("id")
            bind_context(user_id=user_id)
            
            # Set Sentry user context
            set_user_context(
                user_id=user_id,
                username=request.state.user.get("username"),
            )
        
        # Log request
        logger.debug(
            "request_started",
            client_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        
        # Track request duration
        start_time = time.time()
        
        try:
            # Process request
            response = await call_next(request)
            
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000
            
            # Log response
            logger.debug(
                "request_completed",
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
            )
            
            # Add custom headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"
            
            return response
            
        except Exception as e:
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000
            
            # Log error
            logger.error(
                "request_failed",
                error_type=type(e).__name__,
                error_message=str(e),
                duration_ms=round(duration_ms, 2),
                exc_info=True,
            )
            
            # Add Sentry breadcrumb
            add_breadcrumb(
                message=f"Request failed: {type(e).__name__}",
                category="error",
                level="error",
                data={
                    "error": "Internal server error",
                    "duration_ms": duration_ms,
                }
            )
            
            raise
            
        finally:
            # Unbind context
            unbind_context("request_id", "method", "path")
            if user_id:
                unbind_context("user_id")


class PerformanceLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that logs slow requests.
    
    Helps identify performance bottlenecks.
    """
    
    def __init__(self, app: ASGIApp, slow_threshold_ms: float = 1000):
        super().__init__(app)
        self.slow_threshold_ms = slow_threshold_ms
        self.long_poll_paths = ("/api/worker-agent/poll",)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        
        response = await call_next(request)
        
        duration_ms = (time.time() - start_time) * 1000
        
        # Log slow requests
        if duration_ms > self.slow_threshold_ms and request.url.path not in self.long_poll_paths:
            logger.warning(
                "slow_request",
                method=request.method,
                path=request.url.path,
                duration_ms=round(duration_ms, 2),
                threshold_ms=self.slow_threshold_ms,
            )
            
            # Add Sentry breadcrumb
            add_breadcrumb(
                message=f"Slow request: {request.method} {request.url.path}",
                category="performance",
                level="warning",
                data={
                    "duration_ms": duration_ms,
                    "threshold_ms": self.slow_threshold_ms,
                }
            )
        
        return response


class ErrorLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that logs all errors with full context.
    
    Captures:
    - Exception details
    - Request context
    - User context
    - Stack trace
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            return await call_next(request)
        except Exception as e:
            # Log error with full context
            logger.error(
                "unhandled_exception",
                error_type=type(e).__name__,
                error_message=str(e),
                method=request.method,
                path=request.url.path,
                query_params=dict(request.query_params),
                exc_info=True,
            )
            
            raise
