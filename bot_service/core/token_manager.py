# bot_service/core/token_manager.py
"""
Unified token manager for user platform tokens.
"""
import logging
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from core.token_utils import get_user_token_from_db

logger = logging.getLogger(__name__)


class TokenManager:
    """
    Unified manager for working with user tokens.

    Only checks the token ``is_active`` flag. Security relies on token
    deactivation during new login flows.
    """

    @staticmethod
    def get_user_token(
        user_id: int,
        platform: str,
        session_id: Optional[str] = None,
        require_session_check: bool = False,
        db: Session = None
    ) -> Optional[str]:
        """
        Return the user access token for a platform.

        Args:
            user_id: User ID
            platform: Platform ('twitch', 'vk', 'donationalerts')
            session_id: Unused, kept for backward compatibility
            require_session_check: Unused, kept for backward compatibility
            db: Optional database session to avoid race conditions

        Returns:
            Access token or ``None`` when missing
        """
        try:
            logger.debug(f"[PACKAGE] [TOKEN MANAGER] Getting token for user {user_id}, platform {platform}")
            tokens = get_user_token_from_db(user_id, platform, db)

            if not tokens:
                logger.warning(f"[ERROR] [TOKEN MANAGER] No token found for user {user_id}, platform {platform}")
                return None

            if not tokens.get("access_token"):
                logger.warning(f"[ERROR] [TOKEN MANAGER] Token exists but access_token is empty for user {user_id}, platform {platform}")
                return None

            logger.debug(f"[OK] [TOKEN MANAGER] Token retrieved for user {user_id}, platform {platform}")
            return tokens["access_token"]

        except Exception as e:
            logger.error(f"[ERROR] [TOKEN MANAGER] Error getting token for user {user_id}, platform {platform}: {e}")
            return None

    @staticmethod
    def get_user_token_data(
        user_id: int,
        platform: str,
        session_id: Optional[str] = None,
        require_session_check: bool = False,
        db: Session = None
    ) -> Optional[Dict[str, Any]]:
        """
        Return the full token payload, not only the access token.
        """
        try:
            logger.debug(f"[PACKAGE] [TOKEN MANAGER] Getting token DATA for user {user_id}, platform {platform}")
            return get_user_token_from_db(user_id, platform, db)

        except Exception as e:
            logger.error(f"[ERROR] [TOKEN MANAGER] Error getting token data for user {user_id}, platform {platform}: {e}")
            return None


# Singleton instance
token_manager = TokenManager()

