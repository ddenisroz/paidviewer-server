"""CSRF protection middleware using double-submit cookie validation."""

import logging
import secrets

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class CSRFProtectionMiddleware(BaseHTTPMiddleware):
    """Protect state-changing endpoints from CSRF attacks."""

    def __init__(self, app, secret_key: str, exempt_paths: list | None = None):
        super().__init__(app)
        self.secret_key = secret_key
        self.exempt_paths = exempt_paths or [
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/auth/twitch",
            "/auth/vk",
            "/auth/twitch/callback",
            "/auth/vk/callback",
            "/api/auth/dev-login",
            # Third-party MemeAlerts SPA performs its own POST requests through our
            # same-origin proxy while keeping our session cookie attached.
            "/api/memealerts/proxy",
        ]

    async def dispatch(self, request: Request, call_next):
        if self._is_exempt_path(request.url.path):
            return await call_next(request)

        if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
            has_session_cookie = bool(request.cookies.get("session_id"))
            if has_session_cookie and (not await self._validate_csrf_token(request)):
                logger.warning(
                    "CSRF validation failed for %s %s", request.method, request.url.path
                )
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "CSRF token validation failed"},
                )

        response = await call_next(request)

        # Keep CSRF token stable across the session. Rotating it on every GET
        # breaks clients/tests that fetched token once and then perform POST/PUT.
        if request.method == "GET" and request.url.path.startswith("/api/"):
            csrf_token = request.cookies.get("csrf_token") or self._generate_csrf_token(
                request
            )
            forwarded_proto = (
                (request.headers.get("x-forwarded-proto") or "")
                .split(",")[0]
                .strip()
                .lower()
            )
            is_secure_request = (
                request.url.scheme == "https" or forwarded_proto == "https"
            )
            response.set_cookie(
                "csrf_token",
                csrf_token,
                httponly=False,
                secure=is_secure_request,
                samesite="strict",
                max_age=3600,
            )

        return response

    def _is_exempt_path(self, path: str) -> bool:
        """Check whether path is exempt from CSRF validation."""
        for exempt in self.exempt_paths:
            if path == exempt or path.startswith(f"{exempt}/"):
                return True
        return False

    def _generate_csrf_token(self, request: Request) -> str:
        """Generate CSRF token bound to the current session."""
        import hashlib
        import hmac

        session_id = request.cookies.get("session_id", "")
        if session_id:
            session_hash = hmac.new(
                self.secret_key.encode(),
                session_id.encode(),
                hashlib.sha256,
            ).hexdigest()[:32]
            return f"{session_hash}_{secrets.token_urlsafe(16)}"
        return secrets.token_urlsafe(32)

    async def _validate_csrf_token(self, request: Request) -> bool:
        """Validate CSRF token from header and cookie."""
        csrf_token = request.headers.get("X-CSRF-Token")
        if not csrf_token:
            return False

        cookie_token = request.cookies.get("csrf_token")
        if not cookie_token:
            return False

        return secrets.compare_digest(csrf_token, cookie_token)


def get_csrf_token(request: Request) -> str:
    """Return current CSRF token stored in cookie."""
    return request.cookies.get("csrf_token", "")
