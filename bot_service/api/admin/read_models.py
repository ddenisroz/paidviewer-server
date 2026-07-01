"""Consolidated admin read-model endpoints for the frontend ops center."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from auth.auth import get_current_user
from core.database import get_db
from core.datetime_utils import utcnow_naive
from core.internal_service_auth import (
    TTSAuthConfigError,
    build_tts_auth_headers,
    build_tts_httpx_client_kwargs,
)
from platforms.registry import platform_registry
from repositories.blocked_channel_repository import BlockedChannelRepository
from repositories.system_log_repository import SystemLogRepository
from repositories.whitelisted_channel_repository import WhitelistedChannelRepository
from services.admin import get_admin_stats_service
from services.tts.provider_utils import (
    ProviderRoutingError,
    get_all_provider_capabilities,
    get_synthesis_upstream_url,
    should_route_provider_via_gateway,
)
from services.twitch_bot_oauth_service import twitch_bot_oauth_service
from services.vk_bot_oauth_service import vk_bot_oauth_service
from services.worker_control.service import WorkerControlPlaneService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin-read-models"])
REQUIRED_TWITCH_CHAT_SCOPES = {"chat:read", "chat:edit"}


def require_admin(user: dict) -> None:
    """Ensure the current user has admin access."""
    if not (user.get("role") == "admin" or bool(user.get("is_admin", False))):
        raise HTTPException(status_code=403, detail="Admin access required")


def _format_user_name(user: Any, fallback_id: int | None = None) -> str:
    """Return a friendly user label for admin logs."""
    if user:
        return user.twitch_username or user.vk_username or user.vk_channel_name or f"User {user.id}"
    return f"Unknown {fallback_id}" if fallback_id else "Unknown"


def _channel_to_dict(channel: Any) -> dict[str, Any]:
    """Serialize blocked channel rows."""
    return {
        "id": channel.id,
        "channel_name": channel.channel_name,
        "reason": channel.reason,
        "blocked_by": channel.blocked_by,
        "is_active": channel.is_active,
        "created_at": channel.created_at.isoformat() if channel.created_at else None,
    }


def _read_system_logs_preview(lines: int = 20) -> list[str]:
    """Return a lightweight preview of recent system logs."""
    logs_dir = Path("logs")
    all_logs: list[str] = []

    error_log_file = logs_dir / "errors" / "bot_service_errors.log"
    if error_log_file.exists():
        try:
            with open(error_log_file, "r", encoding="utf-8", errors="ignore") as handle:
                error_lines = handle.readlines()
            all_logs.extend([f"[ERROR] {line.strip()}" for line in error_lines[-max(lines // 2, 1) :] if line.strip()])
        except Exception:
            logger.exception("Could not read error log preview")

    app_log_file = logs_dir / "app" / "bot_service.log"
    if app_log_file.exists():
        try:
            with open(app_log_file, "r", encoding="utf-8", errors="ignore") as handle:
                app_lines = handle.readlines()
            all_logs.extend([line.strip() for line in app_lines[-lines:] if line.strip()])
        except Exception:
            logger.exception("Could not read app log preview")

    all_logs.sort(reverse=True)
    return all_logs[:lines]


def _collect_bot_runtime() -> dict[str, Any]:
    """Read bot runtime status from the registry."""
    from startup.bot_registry import get_bot_registry

    registry = get_bot_registry()
    twitch_bot = registry.twitch_bot
    vk_bot = registry.vk_bot

    twitch_is_ready = False
    if twitch_bot:
        twitch_is_ready = hasattr(twitch_bot, "user_id") and twitch_bot.user_id is not None

    return {
        "twitch": {
            "connected": twitch_bot is not None,
            "channels": len(getattr(twitch_bot, "connected_channels", [])) if twitch_bot else 0,
            "is_ready": twitch_is_ready,
            "is_running": registry.is_twitch_running(),
        },
        "vk": {
            "connected": vk_bot is not None,
            "channels": len(getattr(vk_bot, "connected_channels", [])) if vk_bot else 0,
            "is_running": registry.is_vk_running(),
            "is_ready": bool(getattr(vk_bot, "is_running", False)) if vk_bot else False,
        },
    }


async def _load_bot_token_status(platform: str, db: Session) -> dict[str, Any]:
    """Return token metadata for the requested bot platform."""
    provider = platform.strip().lower()
    service = twitch_bot_oauth_service if provider == "twitch" else vk_bot_oauth_service
    bot_token = await service.get_bot_token(db)

    if not bot_token:
        return {
            "configured": False,
            "platform": provider,
            "message": "Bot token not configured",
        }

    expires_at = bot_token.get("expires_at")
    seconds_left = None
    if expires_at:
        seconds_left = max(0, int((expires_at - utcnow_naive()).total_seconds()))
    scopes = bot_token.get("scopes") if isinstance(bot_token.get("scopes"), list) else []
    missing_scopes = (
        sorted(REQUIRED_TWITCH_CHAT_SCOPES - set(scopes))
        if provider == "twitch"
        else []
    )

    return {
        "configured": True,
        "platform": provider,
        "bot_login": bot_token.get("bot_login"),
        "bot_user_id": bot_token.get("bot_user_id"),
        "scopes": scopes,
        "missing_scopes": missing_scopes,
        "valid_for_chat": not missing_scopes,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "seconds_left": seconds_left,
        "needs_refresh": bool(
            seconds_left is not None and seconds_left <= service.REFRESH_IF_NEEDED_THRESHOLD_SECONDS
        ),
        "has_refresh_token": bool(bot_token.get("refresh_token")),
    }


async def _fetch_provider_health(provider: str) -> dict[str, Any]:
    """Check current upstream health for a TTS provider."""
    normalized_provider = str(provider or "").strip().lower()
    try:
        upstream_url = get_synthesis_upstream_url(normalized_provider).rstrip("/")
    except ProviderRoutingError as error:
        return {
            "provider": normalized_provider,
            "healthy": False,
            "available": False,
            "status": "unconfigured",
            "error_code": str(error),
            "message": str(error),
        }

    use_gateway = should_route_provider_via_gateway(normalized_provider)

    try:
        headers = build_tts_auth_headers(
            provider=normalized_provider,
            upstream="synthesis",
            use_gateway=use_gateway,
            strict=False,
        )
    except TTSAuthConfigError as error:
        return {
            "provider": normalized_provider,
            "healthy": False,
            "available": False,
            "status": "auth_not_configured",
            "url": upstream_url,
            "via": "gateway" if use_gateway else "direct",
            "error_code": "tts_upstream_auth_not_configured",
            "message": str(error),
        }

    try:
        async with httpx.AsyncClient(timeout=5.0, **build_tts_httpx_client_kwargs()) as client:
            response = await client.get(f"{upstream_url}/health", headers=headers)
        payload = response.json() if response.content else {}
        service_status = payload.get("status", "unknown")
        healthy = response.status_code == 200 and service_status in {"healthy", "ok", "up"}
        return {
            "provider": normalized_provider,
            "healthy": healthy,
            "available": response.status_code == 200,
            "status": service_status,
            "url": upstream_url,
            "via": "gateway" if use_gateway else "direct",
            "error_code": None if healthy else "provider_unhealthy",
            "message": None if healthy else payload.get("message") or payload.get("detail"),
        }
    except Exception as error:
        logger.warning("Provider health check unavailable for %s: %s", normalized_provider, error)
        return {
            "provider": normalized_provider,
            "healthy": False,
            "available": False,
            "status": "offline",
            "url": upstream_url,
            "via": "gateway" if use_gateway else "direct",
            "error_code": "provider_unreachable",
            "message": "Сервис не отвечает. Запустите локальный TTS или проверьте адрес.",
            "details": str(error),
        }


def _summarize_workers(workers: list[dict[str, Any]]) -> dict[str, Any]:
    """Build worker counters for admin runtime surfaces."""
    summary = {
        "total": len(workers),
        "online": 0,
        "busy": 0,
        "offline": 0,
        "disabled": 0,
        "managed": 0,
        "self_hosted": 0,
        "providers": {"f5": 0},
    }
    for worker in workers:
        status = str(worker.get("status") or "offline").lower()
        if status in summary:
            summary[status] += 1
        else:
            summary["offline"] += 1

        if worker.get("is_managed"):
            summary["managed"] += 1
        else:
            summary["self_hosted"] += 1

        if worker.get("supports_f5"):
            summary["providers"]["f5"] += 1
    return summary


def _build_alerts(
    *,
    provider_health: dict[str, Any],
    tokens: dict[str, Any],
    workers_summary: dict[str, Any],
) -> list[dict[str, str]]:
    """Create compact alert cards for the overview tab."""
    alerts: list[dict[str, str]] = []

    for provider, health in provider_health.items():
        if not health.get("healthy"):
            alerts.append(
                {
                    "id": f"tts-{provider}",
                    "severity": "high",
                    "title": f"{provider.upper()} не отвечает",
                    "message": health.get("message") or "Проверьте, что голосовой сервис запущен и доступен.",
                }
            )

    for platform, status in tokens.items():
        if not status.get("configured"):
            alerts.append(
                {
                    "id": f"token-{platform}",
                    "severity": "medium",
                    "title": f"{platform.upper()} бот не авторизован",
                    "message": "Нужна авторизация бота перед запуском чата.",
                }
            )
        elif status.get("missing_scopes"):
            alerts.append(
                {
                    "id": f"token-scopes-{platform}",
                    "severity": "high",
                    "title": f"{platform.upper()} бот без прав чата",
                    "message": f"Нет прав: {', '.join(status['missing_scopes'])}. Переавторизуйте бота.",
                }
            )
        elif status.get("needs_refresh"):
            alerts.append(
                {
                    "id": f"token-refresh-{platform}",
                    "severity": "medium",
                    "title": f"{platform.upper()} токен скоро истечёт",
                    "message": "Обновите токен перед следующим запуском.",
                }
            )

    if workers_summary["offline"] > 0:
        alerts.append(
            {
                "id": "workers-offline",
                "severity": "medium",
                "title": "Часть локальных TTS-программ offline",
                "message": f"Не отвечают: {workers_summary['offline']}",
            }
        )

    return alerts


@router.get("/overview")
async def get_admin_overview(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return a compact ops-center overview for the new admin dashboard."""
    require_admin(user)

    stats_service = get_admin_stats_service(db)
    dashboard_stats = stats_service.get_dashboard_stats()
    monitoring_metrics = stats_service.get_monitoring_metrics()
    runtime_bots = _collect_bot_runtime()
    provider_health = {
        "f5": await _fetch_provider_health("f5"),
    }
    worker_service = WorkerControlPlaneService(db)
    workers = worker_service.list_workers_admin()
    worker_summary = _summarize_workers(workers)
    tokens = {
        "twitch": await _load_bot_token_status("twitch", db),
        "vk": await _load_bot_token_status("vk", db),
    }

    whitelist_total = len(WhitelistedChannelRepository(db).get_all())
    blocked_repo = BlockedChannelRepository(db)
    blocked_channels, blocked_total = blocked_repo.get_active_paginated(page=1, limit=5)
    active_channels = stats_service.get_active_channels()

    alerts = _build_alerts(
        provider_health=provider_health,
        tokens=tokens,
        workers_summary=worker_summary,
    )

    return {
        "success": True,
        "data": {
            "stats": dashboard_stats,
            "monitoring": monitoring_metrics,
            "runtime": {
                "bots": runtime_bots,
                "tokens": tokens,
                "workers": {
                    "summary": worker_summary,
                    "items": workers[:6],
                },
            },
            "tts": {
                "official_modes": ["cloud", "self_host"],
                "providers": provider_health,
                "capabilities": get_all_provider_capabilities(),
            },
            "accounts": {
                "whitelist_total": whitelist_total,
                "users_total": dashboard_stats.get("users", {}).get("total", 0),
                "active_today": dashboard_stats.get("users", {}).get("active_today", 0),
            },
            "channels": {
                "active_total": len(active_channels),
                "blocked_total": blocked_total,
                "blocked_preview": [_channel_to_dict(channel) for channel in blocked_channels],
            },
            "platforms": platform_registry.get_configs(),
            "alerts": alerts,
        },
    }


@router.get("/runtime")
async def get_admin_runtime(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return runtime-centric data for the admin Runtime tab."""
    require_admin(user)

    worker_service = WorkerControlPlaneService(db)
    workers = worker_service.list_workers_admin()
    tokens = {
        "twitch": await _load_bot_token_status("twitch", db),
        "vk": await _load_bot_token_status("vk", db),
    }

    return {
        "success": True,
        "data": {
            "bots": _collect_bot_runtime(),
            "tokens": tokens,
            "workers": {
                "summary": _summarize_workers(workers),
                "items": workers,
            },
            "platforms": platform_registry.get_configs(),
        },
    }


@router.get("/tts")
async def get_admin_tts(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return TTS provider matrix and worker availability for the admin TTS tab."""
    require_admin(user)

    worker_service = WorkerControlPlaneService(db)
    workers = worker_service.list_workers_admin()
    provider_capabilities = get_all_provider_capabilities()
    provider_health = {
        "f5": await _fetch_provider_health("f5"),
    }

    providers: dict[str, Any] = {}
    for provider_name, capabilities in provider_capabilities.items():
        if provider_name == "gcloud":
            continue
        providers[provider_name] = {
            "official_modes": ["cloud", "self_host"],
            "health": provider_health.get(provider_name),
            "capabilities": capabilities,
        }

    return {
        "success": True,
        "data": {
            "official_modes": ["cloud", "self_host"],
            "providers": providers,
            "workers": {
                "summary": _summarize_workers(workers),
                "items": workers,
            },
        },
    }


@router.get("/accounts")
async def get_admin_accounts(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return accounts-centric data for the admin Accounts tab."""
    require_admin(user)

    stats_service = get_admin_stats_service(db)
    users_payload = stats_service.get_admin_users_list(page=page, limit=limit, search=search)
    sessions_payload = stats_service.get_sessions_paginated(page=1, limit=10)
    whitelist_entries = WhitelistedChannelRepository(db).get_all()

    whitelist_preview = [
        {
            "id": entry.id,
            "channel_name": entry.channel_name,
            "platform": entry.platform,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
        }
        for entry in whitelist_entries[:10]
    ]

    return {
        "success": True,
        "data": {
            "users": users_payload,
            "sessions": sessions_payload,
            "whitelist": {
                "total": len(whitelist_entries),
                "items": whitelist_preview,
            },
        },
    }


@router.get("/channels")
async def get_admin_channels(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return blocked and active channel data for the Channels tab."""
    require_admin(user)

    stats_service = get_admin_stats_service(db)
    active_channels = stats_service.get_active_channels()
    blocked_repo = BlockedChannelRepository(db)
    blocked_channels, blocked_total = blocked_repo.get_active_paginated(search=search, page=page, limit=limit)

    active_twitch = sum(1 for channel in active_channels if channel.get("platform") == "twitch")
    active_vk = sum(1 for channel in active_channels if channel.get("platform") == "vk")

    return {
        "success": True,
        "data": {
            "active_channels": active_channels,
            "blocked_channels": [_channel_to_dict(channel) for channel in blocked_channels],
            "counts": {
                "active_total": len(active_channels),
                "active_twitch": active_twitch,
                "active_vk": active_vk,
                "blocked_total": blocked_total,
            },
            "pagination": {
                "page": page,
                "limit": limit,
                "total": blocked_total,
                "pages": (blocked_total + limit - 1) // limit if limit > 0 else 0,
            },
        },
    }


@router.get("/logs/overview")
async def get_admin_logs_overview(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    action_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return a consolidated logs snapshot without replacing legacy /api/admin/logs."""
    require_admin(user)

    repo = SystemLogRepository(db)
    logs, total_count = repo.get_filtered_paginated(
        action_type=action_type,
        status=status,
        days=days,
        limit=limit,
        offset=offset,
    )

    user_ids = set()
    for log in logs:
        if log.admin_id:
            user_ids.add(log.admin_id)
        if log.target_user_id:
            user_ids.add(log.target_user_id)
    users_map = repo.get_users_by_ids(list(user_ids))

    recent_logs = []
    for log in logs:
        admin_user = users_map.get(log.admin_id)
        target_user = users_map.get(log.target_user_id) if log.target_user_id else None
        recent_logs.append(
            {
                "id": log.id,
                "admin_id": log.admin_id,
                "admin_name": _format_user_name(admin_user, log.admin_id),
                "action_type": log.action_type,
                "description": log.description,
                "target_user_id": log.target_user_id,
                "target_user_name": _format_user_name(target_user, log.target_user_id) if target_user else None,
                "target_resource": log.target_resource,
                "status": log.status,
                "error_message": log.error_message,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            }
        )

    action_stats = repo.get_action_stats(days)
    top_admins = repo.get_top_admins(days)
    top_admin_ids = [admin_id for admin_id, _ in top_admins]
    top_admin_map = repo.get_users_by_ids(top_admin_ids)

    return {
        "success": True,
        "data": {
            "recent_admin_logs": recent_logs,
            "stats": {
                "total_logs": repo.get_total_count(days),
                "days": days,
                "actions_by_type": [
                    {
                        "action_type": action_name,
                        "total": total,
                        "success": success,
                        "failed": failed,
                    }
                    for action_name, total, success, failed in action_stats
                ],
                "top_admins": [
                    {
                        "admin_id": admin_id,
                        "admin_name": _format_user_name(top_admin_map.get(admin_id), admin_id),
                        "action_count": count,
                    }
                    for admin_id, count in top_admins
                ],
            },
            "actions": repo.get_distinct_action_types(),
            "system_logs_preview": _read_system_logs_preview(),
            "pagination": {
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "pages": (total_count + limit - 1) // limit if limit > 0 else 0,
            },
        },
    }
