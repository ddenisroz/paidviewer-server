# bot_service/repositories/admin_stats_repository.py
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, or_

from core.database import (
    User, UserSettings, ChatMessage, UserSession, 
    SecurityLog, BotCommand, UserToken, WhitelistedChannel
)
from repositories.base_repository import BaseRepository

class AdminStatsRepository:
    """
    Repository for Admin Stats and Dashboard.
    Encapsulates complex aggregation queries.
    """
    def __init__(self, db: Session):
        self.db = db

    # === User Counts ===
    def count_users(self, filter_expr=None) -> int:
        query = self.db.query(User)
        if filter_expr is not None:
             query = query.filter(filter_expr)
        return query.count()

    def count_active_users_since(self, since: datetime) -> int:
        # Note: User model doesn't have last_seen, using created_at as fallback
        return self.db.query(User).filter(User.created_at >= since).count()

    def count_new_users_since(self, since: datetime) -> int:
        return self.db.query(User).filter(User.created_at >= since).count()

    def count_users_by_status(self, is_active: bool = None, is_blocked: bool = None) -> int:
        query = self.db.query(User)
        if is_active is not None:
            query = query.filter(User.is_active == is_active)
        if is_blocked is not None:
            query = query.filter(User.is_blocked == is_blocked)
        return query.count()
    
    def count_tts_enabled_users(self) -> int:
        return self.db.query(User).filter(User.tts_enabled.is_(True)).count()

    # === Message Counts ===
    def count_messages(self, since: datetime = None) -> int:
        query = self.db.query(ChatMessage)
        if since:
            query = query.filter(ChatMessage.timestamp >= since)
        return query.count()
    
    def count_user_messages(self, user_id: int) -> int:
        return self.db.query(ChatMessage).filter(ChatMessage.user_id == user_id).count()

    # === Sessions ===
    def count_active_sessions(self) -> int:
        return self.db.query(UserSession).filter(UserSession.is_active.is_(True)).count()

    def count_user_active_sessions(self, user_id: int) -> int:
        return self.db.query(UserSession).filter(
            UserSession.user_id == user_id, 
            UserSession.is_active.is_(True)
        ).count()
    
    def get_sessions_paginated(self, limit: int, offset: int) -> List[UserSession]:
        return self.db.query(UserSession).order_by(desc(UserSession.created_at)).offset(offset).limit(limit).all()
        
    def count_all_sessions(self) -> int:
        return self.db.query(UserSession).count()
    
    def get_users_by_ids(self, user_ids: List[int]) -> List[User]:
        return self.db.query(User).filter(User.id.in_(user_ids)).all()

    # === Integrations ===
    def count_active_tokens(self, platform: str) -> int:
        return self.db.query(UserToken).filter(
            UserToken.platform == platform,
            UserToken.is_active.is_(True)
        ).count()

    # === Security/Errors ===
    def count_errors_since(self, since: datetime) -> int:
        return self.db.query(SecurityLog).filter(
            SecurityLog.created_at >= since,
            SecurityLog.event_type.in_(['error', 'critical', 'exception'])
        ).count()

    # === Commands ===
    def get_top_commands(self, limit: int = 5) -> List[Tuple[str, int]]:
        return self.db.query(
            BotCommand.command_name,
            func.sum(BotCommand.usage_count).label('total_usage')
        ).filter(
            BotCommand.usage_count > 0
        ).group_by(BotCommand.command_name).order_by(
            func.sum(BotCommand.usage_count).desc()
        ).limit(limit).all()

    # === Channels ===
    def get_active_channels_settings(self) -> List[UserSettings]:
        return self.db.query(UserSettings).filter(UserSettings.chat_enabled.is_(True)).all()

    # === Complex User Management Queries ===
    def get_users_paginated(self, limit: int, offset: int, search: str = None) -> Tuple[List[User], int]:
        query = self.db.query(User)
        if search:
            search_term = f"%{search.lower()}%"
            query = query.filter(
                or_(
                    User.twitch_username.ilike(search_term),
                    User.vk_username.ilike(search_term),
                    User.vk_channel_name.ilike(search_term)
                )
            )
        total = query.count()
        users = query.offset(offset).limit(limit).all()
        return users, total

    def get_active_tokens_for_users(self, user_ids: List[int]) -> List[UserToken]:
        return self.db.query(UserToken).filter(
            UserToken.user_id.in_(user_ids),
            UserToken.access_token.isnot(None),
            UserToken.is_active.is_(True) # Assuming we want active/valid ones mainly, but service checks is_active.
            # Service code: filter(UserToken.user_id.in_(user_ids), UserToken.access_token.isnot(None)).all()
            # Then implementation checks t.is_active. 
            # So let's fetch all tokens with access_token.
        ).all()
    
    def get_whitelisted_channels_by_names(self, names: List[str]) -> List[WhitelistedChannel]:
        return self.db.query(WhitelistedChannel).filter(
            WhitelistedChannel.channel_name.in_(names)
        ).all()
    
    def get_user_with_settings(self, user_id: int) -> Tuple[Optional[User], Optional[UserSettings]]:
        user = self.db.query(User).filter(User.id == user_id).first()
        settings = None
        if user:
            settings = self.db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        return user, settings
