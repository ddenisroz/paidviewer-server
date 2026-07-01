"""bot_service entry point.

The main application logic is split across startup modules:
- `startup/bot_registry.py` for bot registry management
- `startup/bot_initializer.py` for bot initialization
- `startup/lifespan.py` for lifecycle hooks
- `startup/router_registry.py` for centralized router registration
- `api/websocket_endpoints.py` for WebSocket handlers
"""

import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

# === Path Setup ===
_bot_service_root = Path(__file__).parent
if str(_bot_service_root) not in sys.path:
    sys.path.insert(0, str(_bot_service_root))

from core.project_paths import BOT_SERVICE_ROOT  # noqa: E402

env_path = BOT_SERVICE_ROOT / ".env"
logger = logging.getLogger(__name__)
_app = None
analysis_logger = None


def _load_environment() -> None:
    load_dotenv(dotenv_path=env_path, override=True)


def _register_health_routes(app: FastAPI) -> None:
    @app.get("/health")
    async def health_check():
        """Return a basic process health status."""

        return {"status": "healthy", "service": "bot_service"}

    @app.get("/health/live")
    async def health_live():
        """Liveness probe: the process is running."""

        return {"status": "alive", "service": "bot_service"}

    @app.get("/health/ready")
    async def health_ready():
        """Readiness probe: core dependencies are available."""

        checks = {
            "database": "unknown",
            "tts_queue": "unknown",
            "websocket_manager": "unknown",
        }
        ready = True

        db = None
        try:
            from core.database import get_db as _get_db

            db = next(_get_db())
            db.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception:
            logger.exception("Readiness database check failed")
            checks["database"] = "error"
            ready = False
        finally:
            if db is not None:
                db.close()

        try:
            from services.tts.memory_tts_queue import get_memory_tts_queue

            queue_running = bool(get_memory_tts_queue()._running)
            checks["tts_queue"] = "ok" if queue_running else "not_running"
            ready = ready and queue_running
        except Exception:
            logger.exception("Readiness queue check failed")
            checks["tts_queue"] = "error"
            ready = False

        try:
            from services.memory_websocket_manager import get_memory_websocket_manager

            ws_running = bool(get_memory_websocket_manager()._running)
            checks["websocket_manager"] = "ok" if ws_running else "not_running"
            ready = ready and ws_running
        except Exception:
            logger.exception("Readiness websocket manager check failed")
            checks["websocket_manager"] = "error"
            ready = False

        status_code = 200 if ready else 503
        payload = {
            "status": "ready" if ready else "not_ready",
            "service": "bot_service",
            "checks": checks,
        }
        return JSONResponse(status_code=status_code, content=payload)


def create_app() -> FastAPI:
    _load_environment()

    from core.analysis_logging import get_analysis_logger
    from core.app_config import create_app as create_fastapi_app
    from core.config import settings
    from core.middleware import RequestLoggingMiddleware, SecurityHeadersMiddleware
    from core.openapi_config import setup_openapi
    from core.sentry_config import init_sentry
    from core.structured_logging import setup_structured_logging
    from middleware.csrf_protection import CSRFProtectionMiddleware
    from middleware.logging_middleware import (
        ErrorLoggingMiddleware,
        PerformanceLoggingMiddleware,
        StructuredLoggingMiddleware,
    )
    from middleware.rate_limit_middleware import RateLimitMiddleware
    from startup.lifespan import lifespan
    from startup.router_registry import register_all_routers

    init_sentry()
    setup_structured_logging()

    global analysis_logger
    analysis_logger = get_analysis_logger()

    app = create_fastapi_app(lifespan=lifespan)
    setup_openapi(app)

    app.add_middleware(ErrorLoggingMiddleware)
    app.add_middleware(PerformanceLoggingMiddleware, slow_threshold_ms=1000)
    app.add_middleware(StructuredLoggingMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(CSRFProtectionMiddleware, secret_key=settings.secret_key)

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestLoggingMiddleware)

    register_all_routers(app)
    _register_health_routes(app)
    return app


def get_app() -> FastAPI:
    global _app
    if _app is None:
        _app = create_app()
    return _app


def __getattr__(name: str):
    if name == "app":
        return get_app()
    if name in {"bot_instance", "twitch_bot_instance", "vk_live_bot_instance"}:
        from startup.bot_registry import get_bot_registry

        registry = get_bot_registry()
        if name in {"bot_instance", "twitch_bot_instance"}:
            return registry.twitch_bot
        return registry.vk_bot
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if __name__ == "__main__":
    import uvicorn

    _load_environment()
    from core.config import settings

    uvicorn.run(
        "main:create_app",
        factory=True,
        host=settings.bot_service_host,
        port=settings.bot_service_port,
        reload=settings.is_development,
        access_log=False,  # Request logging is already handled by middleware.
        log_config=None,  # Keep a single app-level logging format.
    )
