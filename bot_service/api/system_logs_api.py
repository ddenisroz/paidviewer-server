"""
API for system logs and administrator action history.
Clean Architecture: uses SystemLogRepository for data access.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from core.database import get_db
from core.datetime_utils import utcnow_naive
from auth.auth import get_current_user
from repositories.system_log_repository import SystemLogRepository
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["system-logs"])


def _format_user_name(user, fallback_id: int = None) -> str:
    """Format user display name."""
    if user:
        return user.twitch_username or user.vk_username or f"User {user.id}"
    return f"Unknown {fallback_id}" if fallback_id else "Unknown"


@router.get("/logs")
async def get_system_logs(
    action_type: Optional[str] = None,
    admin_id: Optional[int] = None,
    target_user_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    status: Optional[str] = None,
    days: int = 30,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get filtered administrator action logs."""
    try:
        if not (current_user.get("role") == "admin" or current_user.get("is_admin")):
            raise HTTPException(status_code=403, detail="Admin access required")

        repo = SystemLogRepository(db)
        logs, total_count = repo.get_filtered_paginated(
            action_type=action_type,
            admin_id=admin_id,
            target_user_id=target_user_id,
            status=status,
            days=days,
            limit=limit,
            offset=offset
        )

        # Batch fetch all users (fix N+1 query problem)
        user_ids = set()
        for log in logs:
            if log.admin_id:
                user_ids.add(log.admin_id)
            if log.target_user_id:
                user_ids.add(log.target_user_id)
        users_map = repo.get_users_by_ids(list(user_ids))

        # Format results
        formatted_logs = []
        for log in logs:
            admin_user = users_map.get(log.admin_id)
            target_user = users_map.get(log.target_user_id) if log.target_user_id else None

            formatted_logs.append({
                "id": log.id,
                "admin_id": log.admin_id,
                "admin_name": _format_user_name(admin_user, log.admin_id),
                "action_type": log.action_type,
                "description": log.description,
                "target_user_id": log.target_user_id,
                "target_user_name": _format_user_name(target_user, log.target_user_id) if target_user else None,
                "target_resource": log.target_resource,
                "old_value": log.old_value,
                "new_value": log.new_value,
                "ip_address": log.ip_address,
                "status": log.status,
                "error_message": log.error_message,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None
            })

        return {
            "success": True,
            "data": formatted_logs,
            "pagination": {
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "pages": (total_count + limit - 1) // limit
            },
            "timestamp": utcnow_naive().isoformat()
        }

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting system logs")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/logs/stats")
async def get_logs_statistics(
    days: int = 30,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get log statistics grouped by action type."""
    try:
        if not (current_user.get("role") == "admin" or current_user.get("is_admin")):
            raise HTTPException(status_code=403, detail="Admin access required")

        repo = SystemLogRepository(db)
        
        # Action stats
        action_stats = repo.get_action_stats(days)
        action_data = []
        for action_type, count, success, failed in action_stats:
            action_data.append({
                "action_type": action_type,
                "total": count,
                "success": success,
                "failed": failed,
                "success_rate": round((success / count * 100), 2) if count > 0 else 0
            })

        # Top admins
        admin_stats = repo.get_top_admins(days)
        admin_ids = [admin_id for admin_id, _ in admin_stats]
        users_map = repo.get_users_by_ids(admin_ids)
        
        admin_data = []
        for admin_id, count in admin_stats:
            admin_user = users_map.get(admin_id)
            admin_data.append({
                "admin_id": admin_id,
                "admin_name": _format_user_name(admin_user, admin_id),
                "action_count": count
            })

        return {
            "success": True,
            "data": {
                "actions_by_type": action_data,
                "top_admins": admin_data,
                "total_logs": repo.get_total_count(days),
                "days": days
            },
            "timestamp": utcnow_naive().isoformat()
        }

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting logs statistics")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/logs/actions")
async def get_available_actions(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the list of available action types."""
    try:
        if not (current_user.get("role") == "admin" or current_user.get("is_admin")):
            raise HTTPException(status_code=403, detail="Admin access required")

        repo = SystemLogRepository(db)
        action_types = repo.get_distinct_action_types()

        return {
            "success": True,
            "data": action_types,
            "timestamp": utcnow_naive().isoformat()
        }

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting available actions")
        raise HTTPException(status_code=500, detail="Internal server error")


# Re-export SystemLogRepository for backward compatibility with other modules
# that import SystemLogService from here
class SystemLogService:
    """Backward compatible wrapper - use SystemLogRepository directly."""
    
    @staticmethod
    def log_action(db: Session, admin_id: int, action_type: str, **kwargs):
        repo = SystemLogRepository(db)
        return repo.log_action(admin_id=admin_id, action_type=action_type, **kwargs)
