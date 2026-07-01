# bot_service/api/system_api.py
"""System API endpoints."""

import logging
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from auth.auth import get_current_user
from core.config import settings
from core.database import get_db
from core.datetime_utils import utcnow_naive
from repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/health")
async def health_check():
    """Basic health endpoint."""
    return {
        "status": "healthy",
        "timestamp": utcnow_naive().isoformat(),
        "version": "1.0.0",
    }


@router.get("/status")
async def system_status(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return lightweight system status snapshot."""
    try:
        user_repo = UserRepository(db)
        total_users = user_repo.count_all()
        active_users = user_repo.count_active()

        return {
            "success": True,
            "status": {
                "total_users": total_users,
                "active_users": active_users,
                "uptime": "unknown",
                "version": "1.0.0",
            },
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting system status")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/metrics")
async def get_metrics():
    """Return summarized runtime metrics."""
    try:
        from utils.enhanced_logger import get_system_metrics

        metrics_summary = get_system_metrics()
        return {
            "success": True,
            "metrics": metrics_summary,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting metrics")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/metrics/prometheus")
async def get_prometheus_metrics():
    """Return Prometheus metrics URL metadata."""
    try:
        return {
            "success": True,
            "prometheus_url": f"{settings.backend_url.rstrip('/')}/api/metrics",
            "note": "Access Prometheus metrics at the provided URL",
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting Prometheus URL")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/info")
async def system_info():
    """Return static service metadata."""
    return {
        "name": "TTS Bot Service",
        "version": "1.0.0",
        "description": "Text-to-Speech Bot Service with Multi-Platform Support",
        "features": [
            "Twitch Integration",
            "VK Live Integration",
            "TTS Synthesis",
            "WebSocket Support",
            "Admin Panel",
        ],
    }


@router.post("/generate-api-key")
async def generate_api_key(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate and persist a new API key for admin user."""
    try:
        if not (user.get("role") == "admin" or user.get("is_admin", False)):
            raise HTTPException(status_code=403, detail="Admin access required")

        api_key = secrets.token_urlsafe(32)

        user_repo = UserRepository(db)
        user_obj = user_repo.get_by_id(user["id"])
        if not user_obj:
            raise HTTPException(status_code=404, detail="User not found")

        user_obj.api_key = api_key
        db.commit()

        logger.info("New API key generated for user %s", user["id"])
        return {
            "success": True,
            "api_key": api_key,
            "message": "API key generated successfully",
        }

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error generating API key")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/logs")
async def get_system_logs(
    lines: int = 100,
    user: dict = Depends(get_current_user),
):
    """Return merged recent logs from app and error channels."""
    try:
        if not (user.get("role") == "admin" or user.get("is_admin", False)):
            raise HTTPException(status_code=403, detail="Admin access required")

        logs_dir = Path("logs")
        all_logs: list[str] = []

        error_log_file = logs_dir / "errors" / "bot_service_errors.log"
        if error_log_file.exists():
            try:
                with open(error_log_file, "r", encoding="utf-8", errors="ignore") as f:
                    error_lines = f.readlines()
                    all_logs.extend([f"[ERROR] {line.strip()}" for line in error_lines[-lines // 2 :] if line.strip()])
            except Exception:
                logger.exception("Could not read error log file")

        app_log_file = logs_dir / "app" / "bot_service.log"
        if app_log_file.exists():
            try:
                with open(app_log_file, "r", encoding="utf-8", errors="ignore") as f:
                    app_lines = f.readlines()
                    all_logs.extend([line.strip() for line in app_lines[-lines:] if line.strip()])
            except Exception:
                logger.exception("Could not read app log file")

        all_logs.sort(reverse=True)
        result_logs = all_logs[:lines]

        if not result_logs:
            return {
                "success": True,
                "logs": [
                    "INFO - Logs are empty.",
                    "INFO - Logs are written to bot_service/logs/.",
                    "INFO - Checked: logs/app/bot_service.log and logs/errors/bot_service_errors.log.",
                ],
                "total_lines": 3,
                "note": "No logs found yet",
            }

        return {
            "success": True,
            "logs": result_logs,
            "total_lines": len(result_logs),
            "sources": {
                "error_log": str(error_log_file) if error_log_file.exists() else None,
                "app_log": str(app_log_file) if app_log_file.exists() else None,
            },
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting system logs")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/restart")
async def restart_system(
    user: dict = Depends(get_current_user),
):
    """Explicitly unsupported process restart surface."""
    try:
        if not (user.get("role") == "admin" or user.get("is_admin", False)):
            raise HTTPException(status_code=403, detail="Admin access required")

        logger.warning("System restart requested by user %s", user["id"])
        raise HTTPException(
            status_code=501,
            detail={
                "code": "supervisor_restart_not_supported",
                "message": "Process-level restart is not implemented by this API. Use infrastructure restart or the dedicated bot/TTS admin actions.",
                "supported_actions": [
                    "/api/admin/bot-service/restart",
                    "/api/admin/tts/restart",
                ],
            },
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error restarting system")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/csp-report")
async def csp_report(request: Request):
    """Collect CSP violations from clients."""
    try:
        body = await request.json()
        csp = body.get("csp-report") if isinstance(body, dict) else None
        if isinstance(csp, dict):
            logger.warning(
                "CSP violation: document-uri=%s blocked-uri=%s violated-directive=%s",
                csp.get("document-uri"),
                csp.get("blocked-uri"),
                csp.get("violated-directive"),
            )
        else:
            logger.warning("CSP violation report received")
        return {"success": True, "message": "CSP violation reported"}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error processing CSP report")
        raise HTTPException(status_code=500, detail="Internal server error")
