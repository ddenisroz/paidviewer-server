from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any

from auth.auth import get_current_user, get_current_user_optional
from core.database import get_db

# Schemas
from schemas.stream import PlatformUpdate, StreamUpdateRequest

# Services
from services.stream_info_service import StreamInfoService
from utils.websocket_broadcast import broadcast_stream_info_change
from utils.stream_info_cache import get_cached_stream_info, set_cached_stream_info

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["stream-info"])


def _sanitize_category_id(raw_value: Optional[str]) -> Optional[str]:
    """Normalize category identifiers from mixed payloads."""
    if raw_value is None:
        return None

    normalized = str(raw_value).strip()
    if not normalized:
        return None
    if normalized.lower() in {"none", "null", "undefined"}:
        return None
    return normalized


def _extract_category_id(update: Optional[PlatformUpdate]) -> Optional[str]:
    """Read category id from `category_id` or nested `category.id`."""
    if not update:
        return None

    direct_id = _sanitize_category_id(update.category_id)
    if direct_id:
        return direct_id

    category_obj = update.category
    if category_obj and category_obj.id:
        return _sanitize_category_id(category_obj.id)

    return None


def _build_stream_overrides(platform_name: str, update: Optional[PlatformUpdate]) -> Dict[str, Any]:
    """Build immediate stream-info overrides from update payload."""
    if not update:
        return {}

    overrides: Dict[str, Any] = {}
    if update.title is not None:
        overrides["title"] = update.title

    category_id = _extract_category_id(update)

    if platform_name == "twitch":
        if category_id is not None:
            overrides["game_id"] = category_id
        return overrides

    if platform_name == "vk":
        if category_id is not None:
            overrides["category_id"] = category_id

        if update.category:
            category_payload: Dict[str, Any] = {}
            if category_id is not None:
                category_payload["id"] = category_id

            category_title = update.category.title or update.category.name
            if category_title:
                category_payload["title"] = category_title
                category_payload["name"] = category_title
                overrides["category_name"] = category_title

            if update.category.cover_url:
                category_payload["cover_url"] = update.category.cover_url

            if category_payload:
                overrides["category"] = category_payload

        return overrides

    return overrides


def _merge_stream_info(base_info: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    """Merge stream info dicts preserving nested category payload."""
    merged: Dict[str, Any] = dict(base_info or {})
    for key, value in overrides.items():
        if key == "category" and isinstance(value, dict) and isinstance(merged.get("category"), dict):
            merged["category"] = {**merged["category"], **value}
            continue
        merged[key] = value
    return merged

# Simple in-memory cache for stream info (60 second TTL)

def get_stream_service(db: Session = Depends(get_db)) -> StreamInfoService:
    return StreamInfoService(db)

@router.get("/twitch/stream")
async def get_twitch_stream_basic(user: dict = Depends(get_current_user)):
    """
    Get Twitch stream information (legacy basic info).
    """
    return JSONResponse(content={
        "is_live": False,
        "title": "",
        "category": None,
        "viewers": 0,
        "message": "Basic stream info. Use /api/twitch/stream-info for detailed information."
    })

@router.get("/twitch/stream-info")
async def get_twitch_stream_info(
    user: dict = Depends(get_current_user),
    service: StreamInfoService = Depends(get_stream_service)
):
    """Get detailed Twitch stream information (cached for 30 seconds)."""
    try:
        user_id = user.get("id")
        session_id = user.get("session_id")
        
        # Check cache first
        cached = get_cached_stream_info(user_id, "twitch")
        if cached:
            return JSONResponse(content={"data": cached})
        
        info = await service.get_stream_info(user_id, "twitch", session_id)
        
        # Cache result
        set_cached_stream_info(user_id, "twitch", info)
        
        return JSONResponse(content={"data": info})
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting Twitch stream info")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/vk/stream-info")
async def get_vk_stream_info(
    user: dict = Depends(get_current_user),
    service: StreamInfoService = Depends(get_stream_service)
):
    """Get stream info from VK Live."""
    try:
        user_id = user.get("id")
        session_id = user.get("session_id")

        cached = get_cached_stream_info(user_id, "vk")
        if cached:
            return JSONResponse(content={"data": cached})

        info = await service.get_stream_info(user_id, "vk", session_id)
        set_cached_stream_info(user_id, "vk", info)

        # Adaptation for VK specific response format if needed
        # Service returns unified dict. Frontend might expect 'description' for VK?
        # StreamInfoService doesn't explicitly fetch description unless platform returns it.
        # But VK platform get_stream_info usually includes everything.

        return JSONResponse(content={"data": info})
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting VK stream info")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/stream/update")
async def update_stream(
    request: StreamUpdateRequest,
    user: dict = Depends(get_current_user),
    service: StreamInfoService = Depends(get_stream_service)
):
    """Update stream information (title or category)."""
    """Update stream information (title or category)."""
    logger.info("[STREAM UPDATE] Request received")
    
    try:
        user_id = user.get("id")
        session_id = user.get("session_id")
        results = []
        failures = []
        failed_reasons = {}

        async def _broadcast_stream_info(
            platform_name: str,
            overrides: Optional[Dict[str, Any]] = None,
            prefer_cached_first: bool = False,
        ) -> None:
            try:
                info: Dict[str, Any] = {}
                if prefer_cached_first:
                    info = get_cached_stream_info(user_id, platform_name) or {}

                if not info:
                    info = await service.get_stream_info(user_id, platform_name, session_id)

                if overrides:
                    info = _merge_stream_info(info, overrides)

                set_cached_stream_info(user_id, platform_name, info)
                await broadcast_stream_info_change(user_id, platform_name, info)
            except Exception:
                logger.exception("[STREAM_INFO] Broadcast failed for %s", platform_name)

        # Update Twitch
        if request.twitch:
            title = request.twitch.title
            category_id = _extract_category_id(request.twitch)

            if title is not None or category_id is not None:
                success = await service.update_stream(user_id, "twitch", title, category_id)
                if success:
                    results.append("Twitch updated")
                    await _broadcast_stream_info(
                        "twitch",
                        overrides=_build_stream_overrides("twitch", request.twitch),
                    )
                else:
                    failures.append("Twitch")
                    twitch_reason = service.last_error_by_platform.get("twitch")
                    if twitch_reason:
                        failed_reasons["twitch"] = twitch_reason
                    logger.error("Failed to update Twitch for user %s", user_id)

        # Update VK
        if request.vk:
            title = request.vk.title
            category_id = _extract_category_id(request.vk)

            if title is not None or category_id is not None:
                success = await service.update_stream(user_id, "vk", title, category_id)
                if success:
                    results.append("VK updated")
                    await _broadcast_stream_info(
                        "vk",
                        overrides=_build_stream_overrides("vk", request.vk),
                        prefer_cached_first=True,
                    )
                else:
                    failures.append("VK")
                    vk_reason = service.last_error_by_platform.get("vk")
                    if vk_reason:
                        failed_reasons["vk"] = vk_reason
                    logger.error("Failed to update VK for user %s", user_id)

        if not results and not failures:
            return JSONResponse(content={"success": True, "message": "No changes or updates needed"})

        if failures:
            failed_names = [item.lower() for item in failures]
            message = (
                f"Updated: {', '.join(results)}. Failed: {', '.join(failures)}"
                if results
                else f"Failed to update: {', '.join(failures)}"
            )
            if len(failed_names) == 1:
                single_reason = failed_reasons.get(failed_names[0])
                if single_reason:
                    message = f"{message}. Reason: {single_reason}"
            raise HTTPException(
                status_code=409,
                detail={
                    "message": message,
                    "updated_platforms": [item.replace(" updated", "").lower() for item in results],
                    "failed_platforms": failed_names,
                    "failed_reasons": failed_reasons,
                },
            )

        return JSONResponse(
            content={
                "success": True,
                "message": ", ".join(results),
                "updated_platforms": [item.replace(" updated", "").lower() for item in results],
                "failed_platforms": [],
            }
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error in stream update")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/twitch/categories")
async def search_twitch_categories(
    search: str = "",
    user: dict = Depends(get_current_user_optional),
    service: StreamInfoService = Depends(get_stream_service)
):
    """Search Twitch categories."""
    user_id = user.get("id") if user else None
    categories = await service.search_categories("twitch", search, user_id)
    return JSONResponse(content={"categories": categories})

@router.get("/platforms/{platform_name}/categories")
async def search_platform_categories(
    platform_name: str,
    search: str = "",
    user: dict = Depends(get_current_user_optional),
    service: StreamInfoService = Depends(get_stream_service)
):
    """Generic endpoint to search categories for any platform"""
    user_id = user.get("id") if user else None
    categories = await service.search_categories(platform_name, search, user_id)
    return JSONResponse(content={"categories": categories})

@router.post("/platforms/{platform_name}/stream/update")
async def update_platform_stream(
    platform_name: str,
    title: Optional[str] = None,
    category_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
    service: StreamInfoService = Depends(get_stream_service)
):
    """Generic endpoint to update stream info for any platform"""
    try:
        user_id = user.get("id")
        session_id = user.get("session_id")
        success = await service.update_stream(user_id, platform_name, title, category_id)

        if not success:
            raise HTTPException(status_code=409, detail=f"Failed to update {platform_name}")

        try:
            info = await service.get_stream_info(user_id, platform_name, session_id)
            set_cached_stream_info(user_id, platform_name, info)
            await broadcast_stream_info_change(user_id, platform_name, info)
        except Exception:
            logger.exception("[STREAM_INFO] Broadcast failed for %s", platform_name)
        return JSONResponse(content={"success": True, "message": f"{platform_name} updated"})
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error updating %s stream info", platform_name)
        raise HTTPException(status_code=500, detail="Internal server error")
