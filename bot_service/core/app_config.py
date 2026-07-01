# bot_service/core/app_config.py
"""FastAPI application configuration."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from core.config import settings
import logging

# Imports are kept inside functions to avoid circular dependencies.

def setup_logging():
    """Configure logging with the structured runtime configuration."""
    from core.structured_logging import setup_structured_logging
    
    # Configure logging.
    setup_structured_logging()
    
    # Return the configured logger.
    import logging
    logger = logging.getLogger("bot_service")
    logger.info("=== BOT SERVICE STARTED (Structured Logging) ===")

    return logger

from typing import Optional, Callable

logger = logging.getLogger(__name__)

def create_app(lifespan: Optional[Callable] = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="TTS Bot Service",
        description="Service for managing the TTS bot runtime",
        version="2.0.0",
        lifespan=lifespan
    )

    # Register centralized exception handlers.
    from core.exception_handlers import setup_exception_handlers
    setup_exception_handlers(app)

    # Enable rate limiting.
    from core.security_modern import limiter, rate_limit_handler
    from slowapi.errors import RateLimitExceeded

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

    # CORS configuration.
    cors_origins_list = settings.cors_origins_list
    
    allowed_origins = cors_origins_list
    allow_credentials = True
    if "*" in allowed_origins:
        allow_credentials = False
        logger.warning("CORS wildcard origin detected: forcing allow_credentials=False for security")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=allow_credentials,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-Requested-With",
            "Accept",
            "Origin",
            "X-CSRF-Token",
        ],
        max_age=3600,  # Cache preflight requests for one hour.
    )

    # Static files.
    from .project_paths import FRONTEND_ROOT, TEMP_DIR

    widgets_path = FRONTEND_ROOT / "src" / "widgets"
    if widgets_path.exists():
        app.mount("/widgets", StaticFiles(directory=str(widgets_path)), name="widgets")

    uploads_path = Path("uploads").resolve()
    uploads_path.mkdir(parents=True, exist_ok=True)
    app.mount("/static/uploads", StaticFiles(directory=str(uploads_path)), name="uploads")

    # Audio files.
    temp_audio_dir = TEMP_DIR / "tts_audio"
    temp_audio_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/audio", StaticFiles(directory=str(temp_audio_dir)), name="audio")

    return app

# Shared runtime globals are defined in main.py to avoid duplicate instances.
