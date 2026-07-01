import logging

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

from auth.auth import _extract_authenticated_user_id, get_session_data
from core.config import settings
from services.advanced_rate_limiter import advanced_rate_limiter

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces rate limits on incoming requests
    using the AdvancedRateLimiter service.
    """

    @staticmethod
    def _resolve_identifier(request: Request) -> str:
        """Prefer authenticated user scope over shared proxy IPs."""
        session_data = get_session_data(request)
        if session_data:
            user_id = _extract_authenticated_user_id(session_data)
            if user_id:
                return advanced_rate_limiter._get_identifier(user_id=user_id)
        return advanced_rate_limiter._get_identifier(request=request)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not settings.rate_limit_enabled:
            return await call_next(request)

        # Skip rate limiting for static files and specific paths if needed.
        path = request.url.path
        if request.method.upper() == "OPTIONS":
            return await call_next(request)

        if path.startswith("/static") or path.startswith("/docs") or path.startswith("/openapi.json"):
            return await call_next(request)

        # Determine action based on path.
        action = "default"
        if path.startswith("/api/auth/login"):
            action = "login"
        elif path.startswith("/auth/") and ("/login" in path or "/callback" in path):
            action = "login"
        elif path.startswith("/api/tts/youtube-settings"):
            # Dashboard reads/saves YouTube settings often; use regular API limit.
            action = "api"
        elif path.startswith("/api/tts/status"):
            action = "default"  # Higher limit for passive status checks.
        elif path.startswith("/api/tts"):
            # Read endpoints are polled heavily by dashboard UI; keep strict limits
            # only for mutating/expensive TTS actions (POST/PUT/PATCH/DELETE).
            action = "api" if request.method.upper() == "GET" else "tts"
        elif path.startswith("/api/upload") or path.startswith("/upload"):
            action = "upload"
        elif path.startswith("/api"):
            action = "api"

        # At this stage we rely on limiter's identifier helper (IP fallback etc).
        identifier = self._resolve_identifier(request)

        if not advanced_rate_limiter.check_rate_limit(identifier, action):
            logger.warning("Rate limit exceeded for %s on %s (%s)", identifier, path, action)
            retry_after = advanced_rate_limiter._estimate_retry_after(action)
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too Many Requests",
                    "message": "Too many requests. Please retry later.",
                },
                headers={
                    "Retry-After": str(retry_after),
                },
            )

        return await call_next(request)
