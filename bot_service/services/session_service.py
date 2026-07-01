# bot_service/services/session_service.py
"""
Service for Session Management.
Handles:
1. Active WebSocket sessions (via ConnectionManager)
2. User Tokens (via UserTokenRepository)
"""
import logging
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session

from core.connection_manager import get_connection_manager
from repositories.user_token_repository import UserTokenRepository
from core.datetime_utils import utcnow_naive
from models.user import UserToken

logger = logging.getLogger(__name__)


class SessionService:
    """
    Business logic for session management.
    """

    def __init__(self, db: Session):
        self.db = db
        self.token_repo = UserTokenRepository(db)
        self.connection_manager = get_connection_manager()

    # === WebSocket Session Management ===

    def get_active_channels(self) -> List[Dict[str, Any]]:
        """Get list of active channels from ConnectionManager."""
        try:
            active_channel_names = self.connection_manager.get_active_channels()
            channels = []

            for channel_name in active_channel_names:
                # Basic platform detection (can be improved)
                platform = 'twitch'
                if channel_name.isdigit():
                    platform = 'vk'

                channels.append({
                    'channel_name': channel_name,
                    'platform': platform,
                    'connected_at': None,  # CM currently doesn't track this publicly active_sessions
                })
            return channels
        except Exception:
            logger.exception("Error getting active channels")
            raise

    def get_active_sessions_details(self) -> List[Dict[str, Any]]:
        """Get detailed info about active sessions."""
        try:
            active_sessions = self.connection_manager.get_active_sessions()
            sessions = []

            for channel_name, session_ids in active_sessions.items():
                platform = 'twitch'
                if channel_name.isdigit():
                    platform = 'vk'

                sessions.append({
                    'channel_name': channel_name,
                    'platform': platform,
                    'session_count': len(session_ids),
                    'session_ids': list(session_ids)
                })
            return sessions
        except Exception:
            logger.exception("Error getting active sessions details")
            raise

    def disconnect_channel(self, channel_name: str, admin_id: int) -> bool:
        """Force disconnect a channel."""
        try:
            success = self.connection_manager.remove_active_session(channel_name, 'admin_disconnect')
            if success:
                logger.info(f"Admin {admin_id} disconnected channel {channel_name}")
            return success
        except Exception:
            logger.exception("Error disconnecting channel {channel_name}")
            raise

    # === Token Management ===

    def get_user_tokens(self, user_id: int) -> List[Dict[str, Any]]:
        """Get formattted tokens for a user."""
        try:
            tokens = self.token_repo.get_all_by_user(user_id)
            return [self._format_token(t) for t in tokens]
        except Exception:
            logger.exception("Error getting tokens for user {user_id}")
            raise

    def refresh_token(self, token_id: int, user_id: int) -> bool:
        """
        Refresh a token's timestamp (dummy refresh logic from original API).
        In a real scenario, this would call external API to refresh OAuth token.
        """
        try:
            # Using repo to find, but we need custom update logic not in standard crud
            # Actually repo doesn't have get_by_id generic exposed cleanly without type hint mixup in base. 
            # Re-using base repo's get_by_id if available, or query directly via DB as repo wrapper.
            
            # Since UserTokenRepository inherits BaseRepository, it has get_by_id.
            token = self.token_repo.get_by_id(token_id)
            
            if not token:
                logger.warning(f"Token {token_id} not found for refresh")
                return False

            if token.user_id != user_id: 
                # Note: Service usually shouldn't enforce permissions (that's API/Auth layer), 
                # but it should enforce data integrity. 
                # We will check ownership here or rely on API to check it.
                # Let's perform check if we trust the input user_id.
                raise ValueError("Access denied to token")

            # Update logic
            token.created_at = utcnow_naive()
            self.db.commit()
            
            logger.info(f"Token {token_id} refreshed by user {user_id}")
            return True
        except ValueError:
            raise
        except Exception:
            self.db.rollback()
            logger.exception("Error refreshing token {token_id}")
            raise

    def get_token_owner(self, token_id: int) -> Optional[int]:
        """Helper to check token ownership."""
        token = self.token_repo.get_by_id(token_id)
        if token:
            return token.user_id
        return None

    def _format_token(self, token: UserToken) -> Dict[str, Any]:
        """Format token for API response."""
        return {
            'id': token.id,
            'platform': token.platform,
            'token_type': getattr(token, 'token_type', 'oauth'), # Field might be missing in model definition shown earlier
            'created_at': token.created_at.isoformat() if token.created_at else None,
            'expires_at': token.expires_at.isoformat() if token.expires_at else None,
            'is_active': getattr(token, 'is_active', True)
        }

