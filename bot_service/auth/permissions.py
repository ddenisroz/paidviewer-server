"""Authorization helpers for authenticated users."""

import logging
from typing import Any, Dict, Optional

from fastapi import HTTPException, status

from services.user_identity_service import UserIdentityService

logger = logging.getLogger(__name__)


def require_platform_token(user: Dict[str, Any], platform: Optional[str] = None) -> None:
    """Ensure the authenticated user has at least one required platform token."""
    if not UserIdentityService.validate_user_data(user):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user payload.")

    integrations = user.get("integrations", {})
    if not integrations:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires a connected platform.",
        )

    if platform and platform not in integrations:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This action requires a connected {platform} platform.",
        )


def require_admin(user: Dict[str, Any]) -> None:
    """Ensure the user has admin privileges."""
    if not (user.get("role") == "admin" or user.get("is_admin", False)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges are required.",
        )


def require_auth(user: Dict[str, Any]) -> None:
    """Ensure a valid authenticated user payload is present."""
    if not user or not UserIdentityService.validate_user_data(user):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )


def has_platform_token(user: Dict[str, Any], platform: str) -> bool:
    """Return `True` when the authenticated user has the requested integration."""
    if not UserIdentityService.validate_user_data(user):
        return False

    integrations = user.get("integrations", {})
    return platform in integrations


def can_manage_stream(user: Dict[str, Any]) -> bool:
    return has_platform_token(user, "twitch")


def can_manage_channel_points(user: Dict[str, Any]) -> bool:
    return has_platform_token(user, "twitch")


def can_manage_vk_live(user: Dict[str, Any]) -> bool:
    return has_platform_token(user, "vk")
