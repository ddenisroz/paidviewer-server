"""
API endpoints for platform configuration
"""
from fastapi import APIRouter, HTTPException
from platforms.registry import platform_registry
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/platforms/config")
async def get_platforms_config():
    """
    Get configuration for all available platforms
    
    Returns:
        List of platform configurations with capabilities
    """
    try:
        configs = platform_registry.get_configs()
        logger.debug("Returning %s platform configurations", len(configs))
        return {"platforms": configs}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting platform configs")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/api/platforms/list")
async def list_platforms():
    """
    Get list of available platform names
    
    Returns:
        List of platform names
    """
    try:
        platforms = platform_registry.get_all()
        platform_names = list(platforms.keys())
        logger.debug("Available platforms: %s", platform_names)
        return {"platforms": platform_names}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error listing platforms")
        raise HTTPException(status_code=500, detail="Internal server error")
