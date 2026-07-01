"""
User Cache Invalidation Helpers
"""
import logging
from sqlalchemy.orm import Session
from core.user_cache import user_cache

logger = logging.getLogger(__name__)


def invalidate_user_cache(user_id: int, reason: str = "unknown"):
    """
    Invalidate the cache for a user.

    Args:
        user_id: User ID
        reason: Invalidation reason for logging
    """
    user_cache.invalidate(user_id)
    logger.info(f"[DELETE] User cache invalidated for user {user_id}: {reason}")


def update_user_role(user_id: int, new_role: str, db: Session):
    """
    Update the user role and invalidate the cache.

    Args:
        user_id: User ID
        new_role: New role ('admin', 'user')
        db: Database session
    """
    from core.database import User
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError(f"User {user_id} not found")
    
    old_role = user.role
    user.role = new_role
    db.commit()
    
    # Invalidate cache after a role change.
    invalidate_user_cache(user_id, f"role changed: {old_role} -> {new_role}")
    
    logger.info(f"[OK] User {user_id} role updated: {old_role} -> {new_role}")


def block_user(user_id: int, reason: str, db: Session):
    """
    Block a user and invalidate the cache.

    Args:
        user_id: User ID
        reason: Blocking reason
        db: Database session
    """
    from core.database import User
    from core.datetime_utils import utcnow_naive
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError(f"User {user_id} not found")
    
    user.is_blocked = True
    user.blocked_reason = reason
    user.blocked_at = utcnow_naive()
    user.is_active = False
    db.commit()
    
    # Invalidate cache after blocking the user.
    invalidate_user_cache(user_id, f"user blocked: {reason}")
    
    logger.warning(f"[WARN] User {user_id} blocked: {reason}")


def unblock_user(user_id: int, db: Session):
    """
    Unblock a user and invalidate the cache.

    Args:
        user_id: User ID
        db: Database session
    """
    from core.database import User
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError(f"User {user_id} not found")
    
    user.is_blocked = False
    user.blocked_reason = None
    user.blocked_at = None
    user.is_active = True
    db.commit()
    
    # Invalidate cache after unblocking the user.
    invalidate_user_cache(user_id, "user unblocked")
    
    logger.info(f"[OK] User {user_id} unblocked")


def update_user_username(user_id: int, platform: str, username: str, db: Session):
    """
    Update a username and invalidate the cache.

    Args:
        user_id: User ID
        platform: Platform ('twitch', 'vk')
        username: New username
        db: Database session
    """
    from core.database import User
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError(f"User {user_id} not found")
    
    if platform == 'twitch':
        user.twitch_username = username
    elif platform == 'vk':
        user.vk_username = username
        user.vk_channel_name = username
    
    db.commit()
    
    # Invalidate cache after updating the username.
    invalidate_user_cache(user_id, f"{platform} username updated: {username}")
    
    logger.info(f"[OK] User {user_id} {platform} username updated: {username}")
