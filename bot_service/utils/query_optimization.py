"""
Query Optimization Utilities
Task 7.4: Database query optimization patterns
"""

from sqlalchemy.orm import Session, joinedload
from typing import Optional
from core.database import User


def get_user_with_settings(db: Session, user_id: int) -> Optional[User]:
    """
    Get user with eagerly loaded settings
    Uses joinedload to fetch related data in a single query
    
    [OK] OPTIMIZED: Reduces N+1 query problem
    """
    return db.query(User).options(
        joinedload(User.settings)  # Eager load user settings
    ).filter(User.id == user_id).first()


def get_user_by_twitch_username(db: Session, username: str) -> Optional[User]:
    """
    Get user by Twitch username (case-insensitive)
    Uses functional index for better performance
    
    [OK] OPTIMIZED: Uses idx_users_twitch_username_lower index
    """
    from sqlalchemy import func
    return db.query(User).filter(
        func.lower(User.twitch_username) == username.lower()
    ).first()


def get_user_by_vk_username(db: Session, username: str) -> Optional[User]:
    """
    Get user by VK username (case-insensitive)
    Uses functional index for better performance
    
    [OK] OPTIMIZED: Uses idx_users_vk_username_lower index
    """
    from sqlalchemy import func
    return db.query(User).filter(
        func.lower(User.vk_username) == username.lower()
    ).first()


def get_active_users(db: Session, role: Optional[str] = None, limit: int = 100):
    """
    Get active users, optionally filtered by role
    Uses composite index for better performance
    
    [OK] OPTIMIZED: Uses idx_users_active_role index
    """
    query = db.query(User).filter(User.is_active.is_(True))

    if role:
        query = query.filter(User.role == role)

    return query.limit(limit).all()


def get_blocked_users(db: Session, limit: int = 100):
    """
    Get blocked users
    Uses partial index for better performance
    
    [OK] OPTIMIZED: Uses idx_users_blocked index
    """
    return db.query(User).filter(
        User.is_blocked.is_(True)
    ).order_by(User.blocked_at.desc()).limit(limit).all()


# Query optimization patterns documentation
"""
EAGER LOADING PATTERNS:

1. joinedload() - Use for one-to-one or small one-to-many relationships
   Example: user.settings, user.profile
   
2. selectinload() - Use for large one-to-many relationships
   Example: user.messages, user.sessions
   
3. subqueryload() - Use for complex relationships
   Example: nested relationships

EXAMPLE USAGE:

# Bad (N+1 queries):
users = db.query(User).all()
for user in users:
    print(user.settings.chat_enabled)  # Triggers separate query for each user

# Good (2 queries total):
users = db.query(User).options(joinedload(User.settings)).all()
for user in users:
    print(user.settings.chat_enabled)  # No additional queries

INDEX USAGE:

1. Case-insensitive lookups:
   - Use func.lower() for username lookups
   - Functional indexes support this pattern
   
2. Composite indexes:
   - Use for queries with multiple WHERE conditions
   - Order matters: most selective column first
   
3. Partial indexes:
   - Use for queries with constant WHERE conditions
   - Smaller index size, faster lookups

QUERY PERFORMANCE TIPS:

1. Always use .limit() for list queries
2. Use .first() instead of .all()[0]
3. Use .count() instead of len(.all())
4. Avoid SELECT * - specify columns when possible
5. Use bulk operations for multiple inserts/updates
"""
