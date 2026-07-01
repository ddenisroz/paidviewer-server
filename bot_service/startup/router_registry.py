"""
Router Registry for centralized router management.

This module provides a centralized way to register and include
all API routers, replacing the 40+ manual imports in main.py.

Usage in main.py:
    from startup.router_registry import register_all_routers
    register_all_routers(app)
"""

from dataclasses import dataclass
from importlib import import_module
from typing import Optional

from fastapi import FastAPI


@dataclass
class RouterConfig:
    """Configuration for a single router."""
    module_path: str
    router_name: str = "router"
    prefix: str = ""
    tags: Optional[list[str]] = None


# All router configurations grouped by category
ROUTER_CONFIGS = {
    "auth": [
        RouterConfig("api.auth_api", prefix="", tags=["auth"]),
    ],
    "websocket": [
        RouterConfig("api.websocket_endpoints"),
    ],
    "features": [
        RouterConfig("api.tts", router_name="tts_router"),
        RouterConfig("api.youtube.routes", router_name="youtube_router"),
        RouterConfig("api.youtube.settings_routes", router_name="youtube_settings_router"),
        RouterConfig("api.drops"),
        RouterConfig("api.commands"),
    ],
    "api": [
        RouterConfig("api.moderation_api"),
        RouterConfig("api.database_management_api"),
        RouterConfig("api.points_api_endpoints", router_name="points_router"),
        RouterConfig("api.session_api"),
        RouterConfig("api.bot_control_api"),
        RouterConfig("api.chat_analysis_api"),
        RouterConfig("api.stream_info_api"),
        RouterConfig("api.additional_api"),
        RouterConfig("api.dashboard_api"),
        RouterConfig("api.obs_integration_api"),
        RouterConfig("api.system_api"),
        RouterConfig("api.user_settings_api"),
        RouterConfig("api.chatbox_api"),
        RouterConfig("api.errors_api"),
    ],
    "auth_providers": [
        RouterConfig("auth.vk_auth"),
        RouterConfig("auth.twitch_auth"),
        RouterConfig("auth.twitch_bot_oauth"),
        RouterConfig("auth.vk_bot_oauth"),
        RouterConfig("api.twitch_api_badges", prefix="/api/twitch", tags=["twitch-badges"]),
        RouterConfig("api.twitch_predictions_api"),
        RouterConfig("api.twitch_polls_api"),
        RouterConfig("api.twitch_interactive_api"),
        RouterConfig("api.vk_api"),
        RouterConfig("api.vk_channel_points_api"),
        RouterConfig("auth.donationalerts_auth"),
    ],
    "admin": [
        RouterConfig("api.admin.router"),
        RouterConfig("api.admin.users_management"),
        RouterConfig("api.database_health_api"),
        RouterConfig("api.system_logs_api"),
    ],
    "other": [
        RouterConfig("api.widgets"),
        RouterConfig("api.active_channels_api"),
        RouterConfig("api.stream_history_api"),
        RouterConfig("api.donationalerts_api"),
        RouterConfig("api.memealerts_api"),
        RouterConfig("api.memealerts_proxy"),
        RouterConfig("api.platforms_api"),
        RouterConfig("api.proxy_api"),
    ],
}

# Order in which router groups should be registered
ROUTER_ORDER = ["auth", "websocket", "features", "api", "auth_providers", "admin", "other"]


def _load_router(config: RouterConfig):
    """Dynamically import and return a router from its configuration."""
    module = import_module(config.module_path)
    return getattr(module, config.router_name)


def register_all_routers(app: FastAPI) -> None:
    """
    Register all routers with the FastAPI application.
    
    This replaces the 40+ manual imports and include_router calls in main.py
    with a single function call.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    registered_count = 0
    
    for group_name in ROUTER_ORDER:
        configs = ROUTER_CONFIGS.get(group_name, [])
        for config in configs:
            try:
                router = _load_router(config)
                include_kwargs = {}
                if config.prefix:
                    include_kwargs["prefix"] = config.prefix
                if config.tags:
                    include_kwargs["tags"] = config.tags
                
                app.include_router(router, **include_kwargs)
                registered_count += 1
            except ImportError as e:
                logger.error(f"Failed to import router from {config.module_path}: {e}")
            except AttributeError as e:
                logger.error(f"Router '{config.router_name}' not found in {config.module_path}: {e}")
            except Exception:
                logger.exception(
                    f"Unexpected error while loading router from {config.module_path}"
                )
    
    logger.debug("Registered %s routers", registered_count)


def get_router_count() -> int:
    """Return the total number of configured routers."""
    return sum(len(configs) for configs in ROUTER_CONFIGS.values())
