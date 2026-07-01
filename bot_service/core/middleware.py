"""Middleware for FastAPI application."""

import logging
import secrets
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach security-related response headers."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        request_path = request.url.path or ""

        # Use per-response nonce for strict CSP.
        script_nonce = secrets.token_urlsafe(16)

        csp_policy = (
            f"default-src 'self'; "
            f"script-src 'self' 'nonce-{script_nonce}' https://cdn.jsdelivr.net https://cdn.socket.io; "
            f"style-src 'self' 'nonce-{script_nonce}' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
            f"img-src 'self' data: https: blob:; "
            f"connect-src 'self' ws: wss: https://api.twitch.tv https://api.vk.com https://www.youtube.com; "
            f"font-src 'self' data: https://fonts.gstatic.com; "
            f"media-src 'self' https: blob:; "
            f"object-src 'none'; "
            f"base-uri 'self'; "
            f"form-action 'self'; "
            f"frame-ancestors 'self' https://www.youtube.com https://twitch.tv; "
            f"upgrade-insecure-requests; "
            f"require-sri-for script style"
        )

        # MemeAlerts proxy serves third-party SPA with inline scripts/styles.
        # Global strict CSP blocks it and causes a blank popup page.
        if not request_path.startswith("/api/memealerts/proxy"):
            response.headers["Content-Security-Policy"] = csp_policy
            response.headers["Content-Security-Policy-Report-Only"] = (
                f"script-src 'self' 'nonce-{script_nonce}'; "
                f"report-uri /api/csp-report"
            )

        forwarded_proto = (
            (request.headers.get("x-forwarded-proto") or "")
            .split(",")[0]
            .strip()
            .lower()
        )
        is_https_request = request.url.scheme == "https" or forwarded_proto == "https"
        if is_https_request:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

        response.headers["X-Content-Type-Options"] = "nosniff"
        # Keep SAMEORIGIN for OBS embed compatibility.
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), "
            "microphone=(), "
            "camera=(), "
            "payment=(), "
            "usb=(), "
            "magnetometer=(), "
            "gyroscope=(), "
            "accelerometer=()"
        )

        # Expose nonce for debugging/optional client use.
        response.headers["X-Script-Nonce"] = script_nonce

        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for request logging."""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        user_info = "Anonymous"
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            try:
                # Reserved for token decode if needed in future.
                pass
            except Exception:
                pass

        response = await call_next(request)

        process_time = time.time() - start_time

        if self.should_log_request(request.url.path, response.status_code):
            log_message = (
                f"{request.method} {request.url.path} - "
                f"Status: {response.status_code} - "
                f"Time: {process_time:.3f}s - "
                f"User: {user_info} - "
                f"IP: {request.client.host if request.client else 'unknown'}"
            )

            if response.status_code >= 400:
                logger.warning(log_message)
            else:
                logger.info(log_message)

        return response

    def should_log_request(self, path: str, status_code: int) -> bool:
        """Return True when request should be logged."""
        if path.startswith(("/static/", "/audio/", "/widgets/", "/favicon.ico")):
            return False

        if path in ["/health", "/metrics", "/ping"]:
            return False

        if path == "/api/worker-agent/poll":
            return status_code >= 400

        if path == "/api/tts/obs-status":
            return status_code >= 400

        if path in {
            "/api/chat/status",
            "/api/auth/status",
            "/api/auth/ws-token",
            "/api/tts/status",
            "/api/youtube/queue",
        }:
            return status_code >= 400

        if status_code == 401:
            polling_endpoints = [
                "/api/user-settings/",
                "/api/chat/status",
                "/api/auth/status",
            ]
            if any(path.startswith(endpoint) for endpoint in polling_endpoints):
                return False

        if status_code in [403, 404]:
            return False

        if status_code >= 500:
            return True

        if status_code >= 400:
            return True

        if path.startswith("/api/"):
            return True

        if path.startswith("/ws/"):
            return True

        return False
