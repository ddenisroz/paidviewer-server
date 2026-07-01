# bot_service/api/monitoring_api.py
"""
API endpoints for system monitoring.
"""
from fastapi import APIRouter, Depends, HTTPException
from auth.auth import get_current_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])


@router.get("/cache/stats")
async def get_cache_stats(user: dict = Depends(get_current_user)):
    """
    Get token-validation cache statistics.
    
    Requires authentication. Available to all authenticated users.
    
    Returns:
        dict: Cache statistics such as entry count and TTL.
    """
    from core.token_validation_cache import token_validation_cache

    stats = token_validation_cache.get_stats()

    return {
        "success": True,
        "cache": {
            "type": "token_validation",
            "total_entries": stats["total_entries"],
            "ttl_seconds": stats["ttl_seconds"],
            "ttl_minutes": round(stats["ttl_seconds"] / 60, 1)
        },
        "info": "Cache reduces HTTP requests to platform APIs by ~90%"
    }


@router.post("/cache/clear")
async def clear_cache(user: dict = Depends(get_current_user)):
    """
    Clear the token-validation cache (admin only).
    
    Requires administrator privileges.
    """
    if not (user.get("role") == "admin" or user.get("is_admin")):
        raise HTTPException(status_code=403, detail="Admin access required")

    from core.token_validation_cache import token_validation_cache

    token_validation_cache.clear()

    logger.info(f"[DELETE] Cache cleared by admin user {user.get('id')}")

    return {
        "success": True,
        "message": "Cache cleared successfully"
    }


@router.post("/cache/cleanup")
async def cleanup_expired_cache(user: dict = Depends(get_current_user)):
    """
    Remove expired cache entries (admin only).
    
    This is normally done automatically, but can also be triggered manually.
    """
    if not (user.get("role") == "admin" or user.get("is_admin")):
        raise HTTPException(status_code=403, detail="Admin access required")

    from core.token_validation_cache import token_validation_cache

    token_validation_cache.cleanup_expired()

    logger.info(f"[CLEANUP] Cache cleanup triggered by admin user {user.get('id')}")

    return {
        "success": True,
        "message": "Expired entries cleaned up"
    }

