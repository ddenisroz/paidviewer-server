# bot_service/core/permissions.py
"""Role- and permission-based access control helpers."""

import logging
from enum import Enum
from functools import wraps
from typing import Callable, List

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


class AppRole(Enum):
    """Application-level roles."""

    ADMIN = "admin"
    USER = "user"


class Permission(Enum):
    """Granular permissions for different operations."""

    MANAGE_USERS = "manage_users"
    MANAGE_GLOBAL_VOICES = "manage_global_voices"
    VIEW_ALL_SETTINGS = "view_all_settings"
    MANAGE_SYSTEM = "manage_system"
    BLOCK_USERS = "block_users"

    MANAGE_OWN_SETTINGS = "manage_own_settings"
    MANAGE_OWN_VOICES = "manage_own_voices"
    MANAGE_STREAM = "manage_stream"
    MANAGE_BOTS = "manage_bots"
    MANAGE_COMMANDS = "manage_commands"
    MANAGE_REWARDS = "manage_rewards"
    MANAGE_DROPS = "manage_drops"
    VIEW_CHAT = "view_chat"
    VIEW_PUBLIC_DATA = "view_public_data"


class PlatformRole(Enum):
    """Platform-specific roles (Twitch, VK)."""

    BROADCASTER = "broadcaster"
    MODERATOR = "moderator"
    VIP = "vip"
    SUBSCRIBER = "subscriber"
    VIEWER = "viewer"
    OWNER = "owner"


ROLE_HIERARCHY = {
    AppRole.ADMIN: [
        Permission.MANAGE_USERS,
        Permission.MANAGE_GLOBAL_VOICES,
        Permission.VIEW_ALL_SETTINGS,
        Permission.MANAGE_SYSTEM,
        Permission.BLOCK_USERS,
        Permission.MANAGE_OWN_SETTINGS,
        Permission.MANAGE_OWN_VOICES,
        Permission.MANAGE_STREAM,
        Permission.MANAGE_BOTS,
        Permission.MANAGE_COMMANDS,
        Permission.MANAGE_REWARDS,
        Permission.MANAGE_DROPS,
        Permission.VIEW_CHAT,
        Permission.VIEW_PUBLIC_DATA,
    ],
    AppRole.USER: [
        Permission.MANAGE_OWN_SETTINGS,
        Permission.MANAGE_OWN_VOICES,
        Permission.MANAGE_STREAM,
        Permission.MANAGE_BOTS,
        Permission.MANAGE_COMMANDS,
        Permission.MANAGE_REWARDS,
        Permission.MANAGE_DROPS,
        Permission.VIEW_CHAT,
        Permission.VIEW_PUBLIC_DATA,
    ],
}

PLATFORM_ROLE_HIERARCHY = {
    PlatformRole.BROADCASTER: 5,
    PlatformRole.OWNER: 5,
    PlatformRole.MODERATOR: 4,
    PlatformRole.VIP: 3,
    PlatformRole.SUBSCRIBER: 2,
    PlatformRole.VIEWER: 1,
}


def has_permission(user_role: AppRole, required_permission: Permission) -> bool:
    if user_role not in ROLE_HIERARCHY:
        logger.warning("Unknown role: %s", user_role)
        return False

    return required_permission in ROLE_HIERARCHY[user_role]


def get_platform_roles(user, platform: str = "twitch") -> List[PlatformRole]:
    roles = [PlatformRole.VIEWER]

    if platform == "twitch":
        if getattr(user, "twitch_is_broadcaster", False):
            roles.append(PlatformRole.BROADCASTER)
        if getattr(user, "twitch_is_moderator", False):
            roles.append(PlatformRole.MODERATOR)
        if getattr(user, "twitch_is_vip", False):
            roles.append(PlatformRole.VIP)
        if getattr(user, "twitch_is_subscriber", False):
            roles.append(PlatformRole.SUBSCRIBER)
    elif platform == "vk":
        if getattr(user, "vk_is_owner", False):
            roles.append(PlatformRole.OWNER)
        if getattr(user, "vk_is_moderator", False):
            roles.append(PlatformRole.MODERATOR)

    return roles


def has_platform_role(user, required_role: PlatformRole, platform: str = "twitch") -> bool:
    user_roles = get_platform_roles(user, platform)
    required_level = PLATFORM_ROLE_HIERARCHY.get(required_role, 0)

    for role in user_roles:
        user_level = PLATFORM_ROLE_HIERARCHY.get(role, 0)
        if user_level >= required_level:
            return True

    return False


def require_permission(required_permission: Permission):
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get("current_user")
            if not current_user:
                for arg in args:
                    if hasattr(arg, "role"):
                        current_user = arg
                        break

            if not current_user:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

            user_role_str = current_user.get("role", "user") if isinstance(current_user, dict) else getattr(current_user, "role", "user")
            user_id = current_user.get("id", "unknown") if isinstance(current_user, dict) else getattr(current_user, "id", "unknown")
            try:
                user_role = AppRole(user_role_str)
            except ValueError:
                logger.warning("Invalid role for user %s: %s", user_id, user_role_str)
                user_role = AppRole.USER

            if not has_permission(user_role, required_permission):
                logger.warning(
                    "Permission denied: User %s (role: %s) attempted to access %s",
                    user_id,
                    user_role.value,
                    required_permission.value,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Insufficient permissions: {required_permission.value} is required.",
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def require_role(required_role: AppRole):
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get("current_user")
            if not current_user:
                for arg in args:
                    if hasattr(arg, "role"):
                        current_user = arg
                        break

            if not current_user:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

            user_role_str = current_user.get("role", "user") if isinstance(current_user, dict) else getattr(current_user, "role", "user")
            user_id = current_user.get("id", "unknown") if isinstance(current_user, dict) else getattr(current_user, "id", "unknown")
            try:
                user_role = AppRole(user_role_str)
            except ValueError:
                logger.warning("Invalid role for user %s: %s", user_id, user_role_str)
                user_role = AppRole.USER

            if user_role != required_role:
                logger.warning(
                    "Role check failed: User %s (role: %s) attempted to access %s-only endpoint",
                    user_id,
                    user_role.value,
                    required_role.value,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access denied: role {required_role.value} is required.",
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def require_platform_role(required_role: PlatformRole, platform: str = "twitch"):
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            user = kwargs.get("user") or kwargs.get("current_user")
            if not user:
                for arg in args:
                    if hasattr(arg, "role"):
                        user = arg
                        break

            if not user:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

            if not has_platform_role(user, required_role, platform):
                user_id = user.get("id", "unknown") if isinstance(user, dict) else getattr(user, "id", "unknown")
                logger.warning(
                    "Platform role check failed: User %s attempted to access %s-only operation on %s",
                    user_id,
                    required_role.value,
                    platform,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access denied: role {required_role.value} is required on platform {platform}.",
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def check_resource_ownership(user, resource_user_id: int) -> bool:
    user_role_str = getattr(user, "role", "user")
    try:
        user_role = AppRole(user_role_str)
        if user_role == AppRole.ADMIN:
            return True
    except ValueError:
        pass

    user_id = user.get("id") if isinstance(user, dict) else getattr(user, "id", None)
    return user_id == resource_user_id


def require_ownership_or_admin(resource_user_id_param: str = "user_id"):
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get("current_user")
            if not current_user:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

            resource_user_id = kwargs.get(resource_user_id_param)
            if resource_user_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Required parameter is missing: {resource_user_id_param}.",
                )

            if not check_resource_ownership(current_user, resource_user_id):
                user_id = current_user.get("id", "unknown") if isinstance(current_user, dict) else getattr(current_user, "id", "unknown")
                logger.warning(
                    "Ownership check failed: User %s attempted to access resource owned by user %s",
                    user_id,
                    resource_user_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: only owned resources can be accessed.",
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator
