import asyncio
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth.auth import get_current_user, get_current_user_optional
from core.database import get_db
from core.security_modern import limiter

router = APIRouter(prefix="/api/widgets", tags=["widgets"])
DEPRECATED_WIDGET_DETAIL = {
    "code": "legacy_widgets_disabled",
    "message": "Legacy widgets are disabled. Use /api/chatbox/settings and /chat-overlay?token=... instead.",
    "replacement": "/api/chatbox/settings",
}


class WidgetConfig(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    widget_type: str
    config: Dict[str, Any]


# In-memory storage for widget configs: {user_id: {config_id: config_data}}
user_widget_configs: Dict[str, Dict[str, Dict[str, Any]]] = {}
_widget_configs_lock = asyncio.Lock()


def _extract_user_id(current_user: Any) -> Optional[str]:
    """Extract a positive user id from dict or ORM-like object."""
    if not current_user:
        return None

    raw_id = current_user.get("id") if isinstance(current_user, dict) else getattr(current_user, "id", None)
    try:
        user_id = int(raw_id)
    except (TypeError, ValueError):
        return None

    if user_id <= 0:
        return None
    return str(user_id)


def _is_admin(current_user: Any) -> bool:
    if not current_user:
        return False
    if isinstance(current_user, dict):
        return bool(current_user.get("role") == "admin" or current_user.get("is_admin", False))
    return bool(getattr(current_user, "role", None) == "admin" or getattr(current_user, "is_admin", False))


@router.post("/chat/config")
@limiter.limit("60/minute")
async def save_chat_config(
    request: Request,
    config: Dict[str, Any],
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    raise HTTPException(status_code=410, detail=DEPRECATED_WIDGET_DETAIL)

    user_id = _extract_user_id(current_user)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    config_id = str(uuid.uuid4())
    config_data = {
        "id": config_id,
        "user_id": user_id,
        "name": config.get("name", "Untitled Chat Widget"),
        "widget_type": "chat",
        "config": config,
        "created_at": datetime.now().isoformat(),
    }

    async with _widget_configs_lock:
        if user_id not in user_widget_configs:
            user_widget_configs[user_id] = {}
        user_widget_configs[user_id][config_id] = config_data

    return {
        "id": config_id,
        "url": f"/widgets/chat?config={config_id}&user={user_id}",
        "message": "Chat widget configuration saved successfully",
    }


@router.get("/chat/config/{config_id}")
@limiter.limit("60/minute")
async def get_chat_config(
    request: Request,
    config_id: str,
    user_id: Optional[str] = None,
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    raise HTTPException(status_code=410, detail=DEPRECATED_WIDGET_DETAIL)

    current_user_id = _extract_user_id(current_user)
    if not user_id and current_user_id:
        user_id = current_user_id

    if user_id and current_user_id and current_user_id != user_id and not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Access denied")

    if user_id:
        async with _widget_configs_lock:
            if user_id in user_widget_configs and config_id in user_widget_configs[user_id]:
                return user_widget_configs[user_id][config_id]

    return {
        "id": config_id,
        "name": "Default Chat Widget",
        "widget_type": "chat",
        "config": {
            "width": 400,
            "height": 300,
            "backgroundColor": "rgba(0, 0, 0, 0.8)",
            "backgroundImage": "none",
            "borderRadius": 8,
            "borderColor": "#333",
            "borderWidth": 2,
            "messageBg": "rgba(255, 255, 255, 0.1)",
            "messageBorderRadius": 4,
            "messageMargin": 4,
            "messagePadding": 8,
            "fontFamily": "Arial, sans-serif",
            "fontSize": 14,
            "fontWeight": "normal",
            "textColor": "#ffffff",
            "animationDuration": 0.3,
            "animationType": "slide-in",
            "maxMessages": 50,
            "showTimestamps": False,
            "showUserRoles": True,
            "colors": {
                "moderator": "#00ff00",
                "vip": "#ff6b6b",
                "subscriber": "#4ecdc4",
                "normal": "#ffffff",
            },
        },
    }


@router.get("/configs")
@limiter.limit("60/minute")
async def list_widget_configs(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    raise HTTPException(status_code=410, detail=DEPRECATED_WIDGET_DETAIL)

    user_id = _extract_user_id(current_user)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    async with _widget_configs_lock:
        user_configs = user_widget_configs.get(user_id, {})
        configs = [
            {
                "id": config_id,
                "name": config_data.get("name", "Untitled"),
                "widget_type": config_data.get("widget_type", "unknown"),
                "created_at": config_data.get("created_at", ""),
                "url": f"/widgets/{config_data.get('widget_type', 'unknown')}?config={config_id}&user={user_id}",
            }
            for config_id, config_data in user_configs.items()
        ]

    return {"configs": configs, "total": len(configs)}


@router.delete("/config/{config_id}")
@limiter.limit("60/minute")
async def delete_widget_config(
    request: Request,
    config_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    raise HTTPException(status_code=410, detail=DEPRECATED_WIDGET_DETAIL)

    user_id = _extract_user_id(current_user)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    async with _widget_configs_lock:
        if user_id not in user_widget_configs or config_id not in user_widget_configs[user_id]:
            raise HTTPException(status_code=404, detail="Configuration not found")
        del user_widget_configs[user_id][config_id]

    return {"message": "Configuration deleted successfully"}


@router.get("/health")
async def widgets_health():
    async with _widget_configs_lock:
        total_configs = sum(len(configs) for configs in user_widget_configs.values())
        users_count = len(user_widget_configs)

    return {
        "status": "deprecated",
        "detail": DEPRECATED_WIDGET_DETAIL,
        "users_count": users_count,
        "configs_count": total_configs,
        "timestamp": datetime.now().isoformat(),
    }
