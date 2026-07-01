# bot_service/services/account_deletion_service.py
"""
Account deletion service for soft and hard delete flows.
"""

import logging
from typing import Dict
from dataclasses import dataclass

from sqlalchemy.orm import Session

from core.database import (
    User
)
from core.datetime_utils import utcnow_naive
from core.user_cache_invalidation import invalidate_user_cache

logger = logging.getLogger(__name__)


@dataclass
class DeletionResult:
    """Account deletion result."""
    success: bool
    deleted_counts: Dict[str, int]
    message: str


class AccountDeletionService:
    """
    Service responsible for account deletion workflows.
    """
    
    async def soft_delete_account(
        self,
        user_id: int,
        db: Session,
    ) -> DeletionResult:
        """
        Perform soft deletion with data anonymization.
        """
        from repositories.user_repository import UserRepository
        db_user = UserRepository(db).get_by_id(user_id)
        if not db_user:
            raise ValueError(f"User {user_id} not found")
        
        logger.info(f"[ACCOUNT] Starting soft delete for user {user_id}")
        
        # Disconnect bots.
        await self._disconnect_all_bots(db_user)
        
        # Delete related data.
        deleted_counts = self._delete_related_data(user_id, db_user, db)
        
        # Soft delete: mark as deleted.
        db_user.is_blocked = True
        db_user.blocked_reason = "account_deleted"
        db_user.blocked_at = utcnow_naive()
        
        # Anonymize for GDPR compliance.
        db_user.twitch_username = f"deleted_user_{user_id}"
        db_user.vk_username = f"deleted_user_{user_id}"
        db_user.vk_channel_name = None
        
        db.commit()
        
        # Invalidate user cache.
        invalidate_user_cache(user_id, "account deleted")
        
        logger.info(f"[ACCOUNT] Soft deleted user {user_id}: {deleted_counts}")
        
        return DeletionResult(
            success=True,
            deleted_counts=deleted_counts,
            message="Account successfully deleted",
        )
    
    async def hard_delete_account(
        self,
        user_id: int,
        admin_user_id: int,
        db: Session,
    ) -> DeletionResult:
        """
        Permanently delete the account (admin only).
        """
        from repositories.user_repository import UserRepository
        target_user = UserRepository(db).get_by_id(user_id)
        if not target_user:
            raise ValueError(f"User {user_id} not found")
        
        username = target_user.twitch_username or target_user.vk_username or f"user_{user_id}"
        # was_blocked = target_user.is_blocked (unused)
        # blocked_reason = target_user.blocked_reason (unused)
        
        # Physical deletion.
        db.delete(target_user)
        db.commit()
        
        logger.info(
            f"[ACCOUNT] [ADMIN] User {user_id} ({username}) permanently deleted "
            f"by admin {admin_user_id}"
        )
        
        return DeletionResult(
            success=True,
            deleted_counts={"user": 1},
            message=f"User {user_id} permanently deleted",
        )
    
    async def _disconnect_all_bots(self, user: User) -> None:
        """Disconnect all bots from the user's channels."""
        from core.connection_manager import get_connection_manager
        from startup.bot_registry import get_bot_registry

        connection_manager = get_connection_manager()
        registry = get_bot_registry()
        
        # Twitch
        if user.twitch_username:
            connection_manager.disable_tts_for_channel(user.twitch_username.lower())
            logger.info(f"[ACCOUNT] Disconnected Twitch bot from {user.twitch_username}")
        
        # VK
        channel_name = user.vk_channel_name or user.vk_username
        if channel_name:
            try:
                if registry.vk_bot:
                    await registry.vk_bot.disconnect_from_channel(channel_name)
                connection_manager.disable_tts_for_channel(channel_name.lower())
                logger.info(f"[ACCOUNT] Disconnected VK bot from {channel_name}")
            except Exception:
                logger.exception("[ACCOUNT] Error disconnecting VK bot")
    
    def _delete_related_data(
        self, 
        user_id: int, 
        user: User,
        db: Session
    ) -> Dict[str, int]:
        """Delete all related user data."""
        deleted = {}
        
        # Repositories
        # Repositories
        from repositories.user_token_repository import UserTokenRepository
        from repositories.chat_message_repository import ChatMessageRepository
        from repositories.tts_settings_repository import TTSSettingsRepository
        from repositories.whitelisted_channel_repository import WhitelistedChannelRepository
        from repositories.user_session_repository import UserSessionRepository
        from repositories.user_settings_repository import UserSettingsRepository
        from repositories.chatbox_repository import ChatBoxRepository
        from repositories.admin_user_repository import AdminUserRepository

        # UserToken
        deleted['tokens'] = UserTokenRepository(db).delete_all_by_user(user_id)
        
        # UserSession
        deleted['sessions'] = UserSessionRepository(db).delete_by_user_id(user_id)
        
        # TTSUserSettings
        deleted['tts_settings'] = TTSSettingsRepository(db).delete_by_user_id(user_id)
        
        # UserSettings
        deleted['user_settings'] = UserSettingsRepository(db).delete_by_user_id(user_id)
        
        # ChatMessage
        deleted['chat_messages'] = ChatMessageRepository(db).delete_by_user(user_id)
        
        # ChatBoxSettings
        deleted['chatbox_settings'] = ChatBoxRepository(db).delete_by_user_id(user_id)
        
        # WhitelistedChannel
        deleted['whitelist'] = 0
        whitelist_repo = WhitelistedChannelRepository(db)
        if user.twitch_username:
            deleted['whitelist'] += whitelist_repo.delete_by_channel_name(user.twitch_username)
        if user.vk_username:
            deleted['whitelist'] += whitelist_repo.delete_by_channel_name(user.vk_username)
        
        # AdminUser
        admin_repo = AdminUserRepository(db)
        ids = [getattr(user, 'twitch_user_id', None), str(user_id)]
        # Filter None
        ids = [str(x) for x in ids if x]
        deleted['admin'] = admin_repo.delete_by_platform_user_ids(ids)
        
        return deleted


# Singleton instance
account_deletion_service = AccountDeletionService()

