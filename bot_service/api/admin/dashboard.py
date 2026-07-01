# bot_service/api/admin/dashboard.py
"""Admin dashboard API endpoints."""

import logging
import os

import httpx
import psutil
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth.auth import get_current_user
from core.internal_service_auth import TTSAuthConfigError, build_tts_auth_headers, build_tts_httpx_client_kwargs
from core.database import get_db
from core.datetime_utils import utcnow_naive
from services.admin import get_admin_stats_service
from services.tts.provider_utils import (
    ProviderRoutingError,
    get_synthesis_upstream_url,
    should_route_provider_via_gateway,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def require_admin(user: dict):
    """Check whether current user has admin role."""
    if not (user.get("role") == "admin" or user.get("is_admin", False)):
        raise HTTPException(status_code=403, detail="Admin access required")


def _tts_auth_headers(provider: str = "f5", *, use_gateway: bool | None = None) -> dict:
    try:
        return build_tts_auth_headers(
            provider=provider,
            upstream="synthesis",
            use_gateway=use_gateway,
            strict=True,
        )
    except TTSAuthConfigError as error:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "tts_upstream_auth_not_configured",
                "message": str(error),
            },
        ) from error


@router.get("/dashboard/stats")
async def get_dashboard_stats(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return aggregated dashboard stats and runtime bot status."""
    try:
        require_admin(user)

        from services.memory_websocket_manager import get_memory_websocket_manager
        from startup.bot_registry import get_bot_registry

        stats_service = get_admin_stats_service(db)
        dashboard_stats = stats_service.get_dashboard_stats()

        try:
            registry = get_bot_registry()
            twitch_bot = registry.twitch_bot
            vk_bot = registry.vk_bot

            twitch_online = False
            twitch_connections = 0
            if twitch_bot:
                twitch_online = hasattr(twitch_bot, "user_id") and twitch_bot.user_id is not None
                twitch_connections = len(twitch_bot.connected_channels) if hasattr(twitch_bot, "connected_channels") else 0

            vk_online = False
            vk_connections = 0
            if vk_bot:
                vk_online = vk_bot.is_running if hasattr(vk_bot, "is_running") else False
                vk_connections = len(vk_bot.connected_channels) if hasattr(vk_bot, "connected_channels") else 0
        except Exception:
            logger.exception("Error getting bot status for dashboard")
            twitch_online = False
            vk_online = False
            twitch_connections = 0
            vk_connections = 0

        try:
            ws_stats = get_memory_websocket_manager().get_connection_stats()
            total_connections = ws_stats.get("active_connections", 0)
        except Exception:
            logger.exception("Error getting websocket stats for dashboard")
            total_connections = 0

        return {
            "success": True,
            "stats": {
                **dashboard_stats,
                "bots": {
                    "twitch_online": twitch_online,
                    "vk_online": vk_online,
                    "total_connections": total_connections,
                    "twitch_connections": twitch_connections,
                    "vk_connections": vk_connections,
                },
            },
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting dashboard stats")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/list")
async def get_admin_list(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return admin list summary."""
    try:
        require_admin(user)

        stats_service = get_admin_stats_service(db)
        result = stats_service.get_admin_list_stats()

        return {"success": True, **result}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting admin list")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/bots/status")
async def get_bots_status(
    user: dict = Depends(get_current_user),
):
    """Return Twitch and VK bot runtime status."""
    try:
        require_admin(user)

        from startup.bot_registry import get_bot_registry

        registry = get_bot_registry()
        bot_instance = registry.twitch_bot
        vk_live_bot_instance = registry.vk_bot

        twitch_is_ready = False
        if bot_instance:
            twitch_is_ready = hasattr(bot_instance, "user_id") and bot_instance.user_id is not None

        twitch_status = {
            "connected": bot_instance is not None,
            "channels": len(getattr(bot_instance, "connected_channels", [])) if bot_instance else 0,
            "is_ready": twitch_is_ready,
        }

        vk_status = {
            "connected": vk_live_bot_instance is not None,
            "channels": len(getattr(vk_live_bot_instance, "connected_channels", [])) if vk_live_bot_instance else 0,
            "is_running": vk_live_bot_instance.is_running if vk_live_bot_instance else False,
        }

        return {
            "success": True,
            "bots": {
                "twitch": twitch_status,
                "vk": vk_status,
            },
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting bots status")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/tts/status")
async def get_tts_status(
    user: dict = Depends(get_current_user),
):
    """Return TTS service health status for admin dashboard."""
    try:
        require_admin(user)

        try:
            tts_service_url = get_synthesis_upstream_url("f5").rstrip("/")
        except ProviderRoutingError as error:
            raise HTTPException(status_code=400, detail={"code": str(error), "message": str(error)}) from error
        use_gateway = should_route_provider_via_gateway("f5")
        headers = _tts_auth_headers("f5", use_gateway=use_gateway)

        try:
            async with httpx.AsyncClient(timeout=5.0, **build_tts_httpx_client_kwargs()) as client:
                response = await client.get(f"{tts_service_url}/health", timeout=5.0, headers=headers)
                tts_data = response.json()

                service_status = tts_data.get("status", "unknown")
                is_healthy = response.status_code == 200 and service_status in ["healthy", "ok", "up"]

            return {
                "success": True,
                "tts_service": {
                    "healthy": is_healthy,
                    "available": True,
                    "status": service_status,
                    "url": tts_service_url,
                    "via": "gateway" if use_gateway else "direct",
                },
            }
        except Exception:
            logger.exception("TTS health check failed in admin dashboard")
            return {
                "success": True,
                "tts_service": {
                    "healthy": False,
                    "available": False,
                    "error": "Internal server error",
                    "status": "offline",
                    "url": tts_service_url,
                },
            }

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting TTS status")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/monitoring/metrics")
async def get_monitoring_metrics(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return monitoring metrics used by admin dashboard widgets."""
    try:
        require_admin(user)

        stats_service = get_admin_stats_service(db)
        metrics = stats_service.get_monitoring_metrics()

        from core.connection_manager import get_connection_manager

        connection_manager = get_connection_manager()
        active_channels = (
            connection_manager.get_active_channels() if hasattr(connection_manager, "get_active_channels") else []
        )
        twitch_channels = [ch for ch in active_channels if not ch.isdigit()]
        vk_channels = [ch for ch in active_channels if ch.isdigit()]
        tts_enabled_channels = (
            len(connection_manager.tts_enabled_channels) if hasattr(connection_manager, "tts_enabled_channels") else 0
        )

        metrics["channels"] = {
            "active": len(active_channels),
            "twitch": len(twitch_channels),
            "vk": len(vk_channels),
        }
        metrics["tts"] = {
            "enabled_channels": tts_enabled_channels,
            "requests_24h": 0,
        }
        metrics["timestamp"] = utcnow_naive().isoformat()

        return {"success": True, "metrics": metrics}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting monitoring metrics")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/analytics")
async def get_analytics(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return admin analytics snapshot."""
    try:
        logger.info("[STATS] [ANALYTICS] Request from user %s", user.get("id"))
        require_admin(user)

        stats_service = get_admin_stats_service(db)
        analytics = stats_service.get_analytics()

        try:
            cpu_usage = psutil.cpu_percent(interval=0)
            memory_info = psutil.virtual_memory()
            memory_usage = memory_info.percent
            current_process = psutil.Process(os.getpid())
            process_memory_mb = current_process.memory_info().rss / 1024 / 1024
        except Exception:
            logger.warning("[WARN] [ANALYTICS] Could not get system metrics")
            cpu_usage = 0
            memory_usage = 0
            process_memory_mb = 0

        analytics.update(
            {
                "errors_count": 0,
                "last_error": None,
                "uptime_percent": 99.8,
                "avg_response_time": None,
                "cpu_usage": round(cpu_usage, 1),
                "memory_usage": round(memory_usage, 1),
                "process_memory_mb": round(process_memory_mb, 1),
            }
        )

        return {"success": True, "analytics": analytics}

    except HTTPException:
        raise
    except Exception:
        logger.exception("[ERROR] [ANALYTICS] Error getting analytics")
        raise HTTPException(status_code=500, detail="Internal server error")
