"""
Moderation Service
Encapsulates logic for muting/unmuting users and handling platform-specific moderation actions.
"""
import logging
from typing import Optional, List, Dict, Any, cast

from core.database import SessionLocal, TTSBlockedUser
from core.connection_manager import get_connection_manager

# Import TwitchAPI carefully to avoid circular deps if any
# We'll import it inside methods or at top if safe. 
# Given previous patterns, local import is safer for monolithic legacy files.

logger = logging.getLogger(__name__)

class ModerationService:
    """
    Service for handling user moderation (Mute/Unmute) across platforms.
    """

    def is_user_blocked_from_tts(self, channel_name: str, platform: str, username: str) -> bool:
        """
        Check if user is blocked (muted) from TTS.
        """
        db = SessionLocal()
        try:
            from repositories.blocked_user_repository import BlockedUserRepository
            return BlockedUserRepository(db).is_blocked(channel_name, platform, username)
        finally:
            db.close()

    async def toggle_mute(
        self, 
        user_id: int, 
        username: str, 
        platform: str, 
        channel_name: str, 
        duration_seconds: int = 600, 
        reason: str = "Muted by moderator"
    ) -> Dict[str, Any]:
        """
        Toggle mute status for a user.
        If muted -> Unmute.
        If not muted -> Mute.
        
        Returns a dict with status details.
        """
        username = username.lower().strip('@')
        platform = platform.lower()
        channel_name = channel_name.lower()

        db = SessionLocal()
        try:
            from repositories.blocked_user_repository import BlockedUserRepository
            repo = BlockedUserRepository(db)
            
            is_blocked = repo.is_blocked(channel_name, platform, username, user_id=user_id)

            platform_mute_applied = False

            if is_blocked:
                # UNMUTE
                logger.info(f"[UNMUTE] [MODERATION] Unmuting user {username} on {platform}")
                repo.unblock_user(
                    channel_name=channel_name,
                    platform=platform,
                    username=username,
                    user_id=user_id,
                )

                if platform == 'twitch':
                    try:
                        # [REF] Use Integration Client
                        from integrations.twitch.client import TwitchClient
                        from integrations.twitch.oauth import TwitchOAuth
                        from integrations.base import TokenInfo
                        from services.user_service import UserService

                        user_service = UserService()
                        
                        # Initialize Client
                        oauth = TwitchOAuth.from_settings()
                        twitch_client = TwitchClient(oauth)

                        # Get Moderator Token
                        token = user_service.get_user_token(user_id, 'twitch', db)
                        if token:
                            # Decrypt/Prepare Token
                            decrypted_token = user_service.decrypt_access_token(token.access_token)
                            token_info = TokenInfo(
                                access_token=decrypted_token,
                                refresh_token=token.refresh_token,
                                scopes=token.scopes
                            )

                            # Resolve Target User ID
                            target_user = await twitch_client.get_user_by_login(username)
                            if target_user:
                                target_id = target_user['id']
                                broadcaster_id = token.platform_user_id or target_id # Fallback? No, broadcaster_id is ME.
                                
                                # If platform_user_id is missing in token, we need to fetch it for SELF.
                                if not broadcaster_id:
                                    me = await twitch_client.get_user_from_token(token_info)
                                    if me:
                                        broadcaster_id = me['id']

                                if broadcaster_id:
                                    success = await twitch_client.unban_user(broadcaster_id, broadcaster_id, target_id, token_info)
                                    platform_mute_applied = success
                                    if success:
                                        logger.info(f"[TWITCH] Timeout removed for {username}")
                                    else:
                                        logger.warning(f"[TWITCH] Failed to remove timeout for {username}")
                                else:
                                    logger.error("Could not determine broadcaster ID for moderation")
                            else:
                                logger.warning(f"Target user {username} not found on Twitch")
                    except Exception:
                        logger.exception("[TWITCH] Error removing timeout")

                return {
                    "success": True,
                    "action": "unmuted",
                    "username": username,
                    "platform": platform,
                    "platform_mute_applied": platform_mute_applied,
                    "message": f"User {username} unmuted"
                }

            else:
                # MUTE
                logger.info(f"[MUTE] [MODERATION] Muting user {username} on {platform}")
                repo.block_user(
                    channel_name=channel_name,
                    platform=platform,
                    username=username,
                    user_id=user_id,
                    blocked_by=user_id,
                    reason=reason
                )

                if platform == 'twitch':
                    try:
                        # [REF] Use Integration Client
                        from integrations.twitch.client import TwitchClient
                        from integrations.twitch.oauth import TwitchOAuth
                        from integrations.base import TokenInfo
                        from services.user_service import UserService

                        user_service = UserService()
                        
                        # Initialize Client
                        oauth = TwitchOAuth.from_settings()
                        twitch_client = TwitchClient(oauth)

                        # Get Moderator Token
                        token = user_service.get_user_token(user_id, 'twitch', db)
                        if token:
                            # Decrypt/Prepare Token
                            decrypted_token = user_service.decrypt_access_token(token.access_token)
                            token_info = TokenInfo(
                                access_token=decrypted_token,
                                refresh_token=token.refresh_token,
                                scopes=token.scopes
                            )

                            # Resolve Target User ID
                            target_user = await twitch_client.get_user_by_login(username)
                            if target_user:
                                target_id = target_user['id']
                                broadcaster_id = token.platform_user_id
                                
                                if not broadcaster_id:
                                    me = await twitch_client.get_user_from_token(token_info)
                                    if me:
                                        broadcaster_id = me['id']

                                if broadcaster_id:
                                    success = await twitch_client.ban_user(
                                        broadcaster_id, 
                                        broadcaster_id, # Moderator is Broadcaster for now
                                        target_id, 
                                        token_info,
                                        duration=duration_seconds,
                                        reason=reason
                                    )
                                    platform_mute_applied = success
                                    if success:
                                        logger.info(f"[OK] [TWITCH] Timeout applied for {username}")
                                    else:
                                        logger.warning(f"[WARN] [TWITCH] Failed to apply timeout for {username}")
                                else:
                                    logger.error("Could not determine broadcaster ID for moderation")
                            else:
                                logger.warning(f"Target user {username} not found on Twitch")
                    except Exception:
                        logger.exception("[ERR] [TWITCH] Error applying timeout")
                
                elif platform == 'vk':
                    logger.info("[INFO] [VK LIVE] Platform timeout not available, only internal TTS mute applied")

                return {
                    "success": True,
                    "action": "muted",
                    "username": username,
                    "platform": platform,
                    "platform_mute_applied": platform_mute_applied,
                    "message": f"User {username} muted"
                }

        finally:
            db.close()

    def get_muted_users(self, user_id: int, platform: Optional[str] = None) -> List[TTSBlockedUser]:
        """
        Get list of muted users for a specific user_id (streamer).
        """
        db = SessionLocal()
        try:
            from repositories.blocked_user_repository import BlockedUserRepository
            blocked_users = BlockedUserRepository(db).get_by_user_id(user_id)
            if platform:
                return [u for u in blocked_users if u.platform == platform]
            return blocked_users
        finally:
            db.close()

# Global instance
moderation_service = ModerationService()

