# bot_service/services/platform_sync_service.py
"""
Platform Role Synchronization Service

This service synchronizes user roles and channel points from platform APIs
(Twitch, VK) to the local database. It ensures that platform-specific roles
(broadcaster, moderator, VIP, subscriber) are kept up-to-date.
"""

import logging
from typing import Optional, Dict
from sqlalchemy.orm import Session
from core.database import User, ChannelReward
from repositories.user_repository import UserRepository
from repositories.user_token_repository import UserTokenRepository
from repositories.points_repository import PointsRepository
from utils.vk_channel_url import extract_vk_channel_slug

logger = logging.getLogger(__name__)


class PlatformSyncService:
    """Service for synchronizing platform roles and data"""

    def __init__(self):
        self.logger = logging.getLogger('platform_sync')

    @staticmethod
    def _resolve_vk_channel_slug(user: User, user_info: Optional[Dict]) -> Optional[str]:
        """Resolve a VK channel slug from API data first, then stored user data."""
        candidates = []
        if isinstance(user_info, dict):
            channel_obj = user_info.get("channel")
            if isinstance(channel_obj, dict):
                candidates.extend([
                    channel_obj.get("url"),
                    channel_obj.get("channel_url"),
                ])

            channels = user_info.get("channels")
            if isinstance(channels, list):
                for channel in channels:
                    if isinstance(channel, dict):
                        candidates.extend([
                            channel.get("url"),
                            channel.get("channel_url"),
                        ])
                        break

            candidates.extend([
                user_info.get("channel_url"),
                user_info.get("channel"),
            ])

        candidates.extend([
            getattr(user, "vk_channel_name", None),
        ])

        for candidate in candidates:
            slug = extract_vk_channel_slug(candidate)
            if slug and " " not in slug and "/" not in slug:
                return slug
        return None

    @staticmethod
    def _resolve_vk_display_name(user: User, user_info: Optional[Dict], channel_slug: Optional[str]) -> Optional[str]:
        """Resolve a stable VK display name for UI/profile use."""
        if isinstance(user_info, dict):
            for key in ("nick", "login", "username", "screen_name", "name"):
                value = user_info.get(key)
                if value:
                    return str(value).strip()

        for candidate in (getattr(user, "vk_username", None), channel_slug):
            if candidate:
                return str(candidate).strip()
        return None

    async def sync_user_roles(self, user: User, platform: str, db: Session) -> bool:
        """Synchronize user roles from platform API."""
        try:
            if platform == 'twitch':
                return await self._sync_twitch_roles(user, db)
            elif platform == 'vk':
                return await self._sync_vk_roles(user, db)
            else:
                self.logger.warning(f"Unknown platform: {platform}")
                return False
        except Exception:
            self.logger.exception("Error syncing roles for user {user.id} on {platform}")
            return False

    async def _sync_twitch_roles(self, user: User, db: Session) -> bool:
        """Synchronize Twitch-specific roles"""
        try:
            if not user.twitch_username:
                self.logger.debug(f"User {user.id} has no Twitch username, skipping sync")
                return False

            # [REF] Use Integration Client
            from integrations.twitch.client import TwitchClient
            from integrations.twitch.oauth import TwitchOAuth

            # Initialize Client
            oauth = TwitchOAuth.from_settings()
            twitch_client = TwitchClient(oauth)

            # Get active token usage
            token_repo = UserTokenRepository(db)
            token = token_repo.get_active_token(user.id, 'twitch')

            if not token:
                self.logger.debug(f"No active Twitch token for user {user.id}")
                return False

            # Check if user is broadcaster
            # In Twitch every user is a broadcaster of their own channel.
            # We assume True if they have a username.
            user.twitch_is_broadcaster = True

            # Get user info from Twitch to verify/update
            try:
                # Use twitch_username for lookup
                broadcaster_info = await twitch_client.get_user_by_login(user.twitch_username)
                
                if broadcaster_info:
                    # Update profile image if available (future logic)
                    if 'profile_image_url' in broadcaster_info:
                        pass
                    
                    self.logger.info(f"Synced Twitch user {user.twitch_username} (ID: {broadcaster_info.get('id')})")

                self.logger.info(f"Synced Twitch roles for user {user.id}: broadcaster={user.twitch_is_broadcaster}")

            except Exception:
                self.logger.exception("Error fetching Twitch user info")

            db.commit()
            return True

        except Exception:
            self.logger.exception("Error syncing Twitch roles")
            db.rollback()
            return False

    async def _sync_vk_roles(self, user: User, db: Session) -> bool:
        """Synchronize VK-specific roles"""
        try:
            if not user.vk_username and not user.vk_channel_name:
                self.logger.debug(f"User {user.id} has no VK username, skipping sync")
                return False

            # [REF] Use Integration Client
            from integrations.vk.client import VKClient
            from integrations.vk.oauth import VKOAuth
            from integrations.base import TokenInfo

            # Initialize Client
            oauth = VKOAuth()
            vk_client = VKClient(oauth)

            # Get user's VK ID from tokens
            token_repo = UserTokenRepository(db)
            token = token_repo.get_active_token(user.id, 'vk')

            if not token:
                self.logger.debug(f"No active VK token for user {user.id}")
                return False

            resolved_channel = self._resolve_vk_channel_slug(user, None)
            if resolved_channel:
                user.vk_channel_name = resolved_channel
            else:
                user.vk_channel_name = None
            user.vk_is_owner = bool(resolved_channel)
            user.vk_is_moderator = False

            # Verify token and user info via API
            try:
                from services.user_service import UserService
                user_service = UserService()
                decrypted_token = user_service.decrypt_access_token(token.access_token)
                token_info = TokenInfo(
                    access_token=decrypted_token,
                    refresh_token=token.refresh_token,
                    scopes=token.scopes
                )

                user_info = await vk_client.get_current_user(token_info)
                if user_info:
                    resolved_channel = self._resolve_vk_channel_slug(user, user_info)
                    user.vk_channel_name = resolved_channel
                    user.vk_is_owner = bool(resolved_channel)
                    user.vk_is_moderator = bool(
                        user_info.get("is_moderator") or user_info.get("moderator")
                    )

                    display_name = self._resolve_vk_display_name(user, user_info, resolved_channel)
                    if display_name:
                        user.vk_username = display_name

                    self.logger.info(
                        "Synced VK user %s (ID: %s, channel=%s, owner=%s, moderator=%s)",
                        user.vk_username,
                        user_info.get('id'),
                        user.vk_channel_name,
                        user.vk_is_owner,
                        user.vk_is_moderator,
                    )
            except Exception:
                self.logger.exception("Error fetching VK user info")

            self.logger.info(
                "Synced VK roles for user %s: owner=%s moderator=%s channel=%s",
                user.id,
                user.vk_is_owner,
                user.vk_is_moderator,
                user.vk_channel_name,
            )

            db.commit()
            return True

        except Exception:
            self.logger.exception("Error syncing VK roles")
            db.rollback()
            return False

    async def _sync_vk_channel_points(self, user: User, db: Session) -> bool:
        """Synchronize VK channel points (if applicable)"""
        try:
            if not user.vk_username or not user.vk_channel_name:
                self.logger.debug(f"User {user.id} missing VK details for points sync")
                return False

            # [REF] Use Integration Client
            from integrations.vk.client import VKClient
            from integrations.vk.oauth import VKOAuth
            from integrations.base import TokenInfo

            oauth = VKOAuth()
            vk_client = VKClient(oauth)
            
            # Get User Token
            token_repo = UserTokenRepository(db)
            token_record = token_repo.get_active_token(user.id, 'vk')
            
            if not token_record or not token_record.access_token:
                return False
                
            from services.user_service import UserService
            user_service = UserService()
            decrypted_token = user_service.decrypt_access_token(token_record.access_token)
            
            token_info = TokenInfo(
                access_token=decrypted_token,
                refresh_token=token_record.refresh_token,
                scopes=token_record.scopes 
            )

            # Get channel rewards
            try:
                # VK Custom Rewards
                rewards = await vk_client.get_custom_rewards(user.vk_channel_name, token_info)

                if not rewards:
                    return True

                points_repo = PointsRepository(db)

                # Sync rewards to database
                for reward_data in rewards:
                    existing_reward = points_repo.get_reward_by_title(
                        user_id=user.id,
                        platform='vk',
                        title=reward_data.get('title')
                    )

                    if existing_reward:
                         existing_reward.cost = reward_data.get('cost', 0)
                         existing_reward.is_enabled = reward_data.get('is_enabled', True)
                    else:
                        new_reward = ChannelReward(
                            user_id=user.id,
                            platform='vk',
                            channel_name=user.vk_channel_name,
                            title=reward_data.get('title'),
                            description=reward_data.get('prompt', ''),
                            cost=reward_data.get('cost', 0),
                            is_enabled=reward_data.get('is_enabled', True),
                            background_color=reward_data.get('background_color', '#0077FF')
                        )
                        db.add(new_reward)

                db.commit()
                self.logger.info(f"Synced {len(rewards)} VK channel rewards for user {user.id}")
                return True

            except Exception:
                self.logger.exception("Error fetching VK rewards")
                return False

        except Exception:
            self.logger.exception("Error syncing VK channel points")
            return False

    async def sync_channel_points(self, user: User, platform: str, db: Session) -> bool:
        """Synchronize channel points/rewards from platform API."""
        try:
            if platform == 'twitch':
                return await self._sync_twitch_channel_points(user, db)
            elif platform == 'vk':
                return await self._sync_vk_channel_points(user, db)
            else:
                self.logger.warning(f"Unknown platform: {platform}")
                return False
        except Exception:
            self.logger.exception("Error syncing channel points for user {user.id} on {platform}")
            return False

    async def _sync_twitch_channel_points(self, user: User, db: Session) -> bool:
        """Synchronize Twitch channel points rewards"""
        try:
            if not user.twitch_username or not user.twitch_is_broadcaster:
                self.logger.debug(f"User {user.id} is not a Twitch broadcaster, skipping channel points sync")
                return False

            # [REF] Use Integration Client
            from integrations.twitch.client import TwitchClient
            from integrations.twitch.oauth import TwitchOAuth
            from integrations.base import TokenInfo

            # Initialize Client
            oauth = TwitchOAuth.from_settings()
            twitch_client = TwitchClient(oauth)
            
            # Get User Token
            token_repo = UserTokenRepository(db)
            token_record = token_repo.get_active_token(user.id, 'twitch')
            
            if not token_record or not token_record.access_token:
                self.logger.warning(f"No active Twitch token for user {user.id}, cannot sync rewards")
                return False
                
            token_info = TokenInfo(
                access_token=token_record.access_token,
                refresh_token=token_record.refresh_token,
                expires_at=token_record.expires_at.timestamp() if token_record.expires_at else None,
                scopes=token_record.scopes 
            )

            # Get platform user ID (channel ID)
            platform_user_id = token_record.platform_user_id
            if not platform_user_id:
                # Try to fetch if missing
                user_info = await twitch_client.get_user_by_login(user.twitch_username)
                if user_info:
                    platform_user_id = user_info['id']
                else:
                    self.logger.error(f"Could not resolve Twitch ID for {user.twitch_username}")
                    return False

            # Get channel rewards from Twitch API
            try:
                rewards = await twitch_client.get_custom_rewards(platform_user_id, token_info)

                if not rewards:
                    self.logger.debug(f"No custom rewards found for user {user.id}")
                    return True

                points_repo = PointsRepository(db)

                # Sync rewards to database
                for reward_data in rewards:
                    # Check if reward already exists
                    existing_reward = points_repo.get_reward_by_title(
                        user_id=user.id,
                        platform='twitch',
                        title=reward_data.get('title')
                    )

                    if existing_reward:
                        # Update existing reward
                        existing_reward.cost = reward_data.get('cost', 0)
                        existing_reward.is_enabled = reward_data.get('is_enabled', True)
                        existing_reward.description = reward_data.get('prompt', '')
                    else:
                        # Create new reward
                        new_reward = ChannelReward(
                            user_id=user.id,
                            platform='twitch',
                            channel_name=user.twitch_username,
                            title=reward_data.get('title'),
                            description=reward_data.get('prompt', ''),
                            cost=reward_data.get('cost', 0),
                            is_enabled=reward_data.get('is_enabled', True),
                            background_color=reward_data.get('background_color', '#9147ff')
                        )
                        db.add(new_reward)

                db.commit()
                self.logger.info(f"Synced {len(rewards)} Twitch channel rewards for user {user.id}")
                return True

            except Exception:
                self.logger.exception("Error fetching Twitch rewards")
                return False

        except Exception:
            self.logger.exception("Error syncing Twitch channel points")
            db.rollback()
            return False

    async def sync_on_login(self, user: User, platform: str, db: Session) -> Dict[str, bool]:
        """Perform full synchronization on user login."""
        try:
            self.logger.info(f"Starting login sync for user {user.id} on {platform}")

            # Sync roles
            roles_synced = await self.sync_user_roles(user, platform, db)

            # Sync channel points (only for broadcasters)
            points_synced = False
            if (platform == 'twitch' and user.twitch_is_broadcaster) or \
               (platform == 'vk' and user.vk_is_owner):
                points_synced = await self.sync_channel_points(user, platform, db)

            return {
                'roles_synced': roles_synced,
                'channel_points_synced': points_synced,
                'success': roles_synced  # At minimum, roles should sync
            }

        except Exception:
            self.logger.exception("Error during login sync")
            return {
                'roles_synced': False,
                'channel_points_synced': False,
                'success': False,
                'error': "Internal server error"
            }

    async def sync_all_users(self, platform: Optional[str] = None, db: Session = None) -> Dict[str, int]:
        """Sync roles for all users (admin operation)."""
        try:
            from core.database import get_db

            if db is None:
                db = next(get_db())

            user_repo = UserRepository(db)
            active_users = user_repo.get_all_active()

            success_count = 0
            failed_count = 0

            for user in active_users:
                # Filter by platform request
                if platform == 'twitch' and not user.twitch_username:
                    continue
                if platform == 'vk' and not user.vk_username:
                    continue

                # Determine which platforms to sync
                platforms_to_sync = []
                if platform:
                    platforms_to_sync = [platform]
                else:
                    if user.twitch_username:
                        platforms_to_sync.append('twitch')
                    if user.vk_username:
                        platforms_to_sync.append('vk')

                # Sync each platform
                for plat in platforms_to_sync:
                    success = await self.sync_user_roles(user, plat, db)
                    if success:
                        success_count += 1
                    else:
                        failed_count += 1

            self.logger.info(f"Bulk sync completed: {success_count} successful, {failed_count} failed")

            return {
                'total_users': len(active_users),
                'success_count': success_count,
                'failed_count': failed_count
            }

        except Exception:
            self.logger.exception("Error during bulk sync")
            return {
                'total_users': 0,
                'success_count': 0,
                'failed_count': 0,
                'error': "Internal server error"
            }


# Global instance
platform_sync_service = PlatformSyncService()

