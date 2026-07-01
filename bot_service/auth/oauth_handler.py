"""Shared OAuth handler for unified cross-platform authorization flows."""
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from urllib.parse import urlencode
from core.datetime_utils import utcnow_naive
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from core.config import settings
from core.database import User, UserSession, UserToken
from core.session_manager import session_manager
from core.token_encryption import encrypt_token
from constants import (
    Platform, ErrorMessages, FRONTEND_REDIRECTS
)
from starlette import status
from core.cookie_config import get_session_cookie_settings
from core.log_sanitizer import mask_session_id
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class OAuthUserData:
    """User data returned by an OAuth provider."""
    platform_user_id: str
    avatar_url: Optional[str]
    access_token: str
    refresh_token: Optional[str]
    expires_at: Optional[datetime]
    scopes: Optional[list]
    username: Optional[str] = None
    channel_name: Optional[str] = None

@dataclass
class OAuthResult:
    """OAuth authorization result."""
    user: User
    session_id: Optional[str]
    is_new_session: bool
    redirect_url: str

class OAuthHandler:
    """Reusable OAuth handler for all supported platforms."""

    def __init__(self):
        self.connection_manager = None

    def _resolve_vk_channel_name(self, user_data: OAuthUserData) -> Optional[str]:
        """Resolve VK channel slug; avoid display names with spaces."""
        if user_data.channel_name:
            candidate = user_data.channel_name.strip()
            if candidate.startswith("http://") or candidate.startswith("https://"):
                candidate = candidate.rstrip("/").split("/")[-1]
            if candidate and " " not in candidate and "/" not in candidate:
                return candidate

        candidate = user_data.username
        if candidate:
            candidate = candidate.strip()
            if candidate.startswith("http://") or candidate.startswith("https://"):
                candidate = candidate.rstrip("/").split("/")[-1]
        if candidate and " " not in candidate and "/" not in candidate:
            return candidate

        return None

    def _apply_vk_profile(self, user: User, user_data: OAuthUserData) -> None:
        """Persist normalized VK profile and role metadata on the user record."""
        vk_channel = self._resolve_vk_channel_name(user_data)
        vk_display = user_data.username or vk_channel

        if vk_channel:
            user.vk_channel_name = vk_channel
            user.vk_is_owner = True
            logger.info(f"Updated VK channel_name: {vk_channel}")
        else:
            user.vk_channel_name = None
            user.vk_is_owner = False
            logger.info("Cleared stale VK channel_name (no channel slug in OAuth data)")

        # VK moderator parity is only safe to set when the provider returns it explicitly.
        user.vk_is_moderator = False

        if vk_display:
            user.vk_username = vk_display

    def _get_connection_manager(self):
        """Lazily import and cache the connection manager."""
        if self.connection_manager is None:
            from core.connection_manager import get_connection_manager
            connection_manager = get_connection_manager()
            self.connection_manager = connection_manager
        return self.connection_manager

    def _deactivate_other_platform_tokens(self, user_id: int, current_platform: str, db: Session):
        """
        Deactivate all user tokens except the token for the current platform.

        Security rule: a fresh login through platform X invalidates tokens for the
        other platforms until they are explicitly reconnected.

        Note: this method does not commit. The caller owns the transaction boundary.
        """
        logger.info(f"[DEACTIVATE] Deactivating other tokens for user {user_id}, keeping {current_platform}")

        other_tokens = db.query(UserToken).filter(
            UserToken.user_id == user_id,
            UserToken.platform != current_platform,
            UserToken.is_active.is_(True)
        ).all()

        if not other_tokens:
            logger.info(f"[DEACTIVATE] No other active tokens found for user {user_id}")
            return

        deactivated_platforms = []
        for token in other_tokens:
            token.is_active = False
            deactivated_platforms.append(token.platform)

        logger.info(f"[DEACTIVATE] Marked for deactivation for user {user_id}: {deactivated_platforms}")

    def get_error_redirect_url(self, platform: str, error_code: str, is_linking: bool = False) -> str:
        """Build a frontend redirect URL for recoverable OAuth errors."""
        base_url = FRONTEND_REDIRECTS["settings"] if is_linking else FRONTEND_REDIRECTS["login"]
        return f"{base_url}?{urlencode({'auth_error': error_code, 'platform': platform})}"

    def normalize_provider_error(self, error: Optional[str]) -> str:
        """Map provider OAuth error codes to user-facing app error codes."""
        normalized = (error or "").strip().lower()
        if normalized in {"access_denied", "cancelled", "canceled", "user_denied", "consent_required"}:
            return "access_denied"
        if normalized in {"temporarily_unavailable", "server_error"}:
            return "provider_unreachable"
        if normalized in {"redirect_mismatch", "invalid_redirect_uri"}:
            return "redirect_mismatch"
        return "provider_rejected"

    def _get_monitored_channel(self, platform: str, user_data: OAuthUserData) -> str:
        """Resolve the monitored channel slug used for session correlation."""
        if platform == Platform.VK:
            vk_channel = self._resolve_vk_channel_name(user_data) or user_data.platform_user_id
            return vk_channel.lower()
        return (user_data.username or user_data.platform_user_id).lower()

    def _get_active_session_for_channel(self, db: Session, channel_name: str) -> Optional[UserSession]:
        """Find an active session already associated with the monitored channel."""
        from sqlalchemy import text

        json_query = "device_info->>'monitored_channel' = :channel"
        return db.query(UserSession).filter(
            UserSession.is_active,
            text(json_query)
        ).params(channel=channel_name).first()

    def _find_identity_matches(self, db: Session, platform: str, user_data: OAuthUserData) -> List[User]:
        """Collect users that already own the current OAuth identity."""
        from sqlalchemy import func

        users_by_id: Dict[int, User] = {}

        matching_tokens = db.query(UserToken).filter(
            UserToken.platform == platform,
            UserToken.platform_user_id == user_data.platform_user_id,
        ).all()
        for token in matching_tokens:
            if not token.user_id:
                continue
            user = db.query(User).filter(User.id == token.user_id).first()
            if user:
                users_by_id[user.id] = user

        if platform == Platform.TWITCH and user_data.username:
            twitch_user = db.query(User).filter(
                func.lower(User.twitch_username) == user_data.username.lower()
            ).first()
            if twitch_user:
                users_by_id[twitch_user.id] = twitch_user

        if platform == Platform.VK:
            if user_data.username:
                vk_user = db.query(User).filter(
                    func.lower(User.vk_username) == user_data.username.lower()
                ).first()
                if vk_user:
                    users_by_id[vk_user.id] = vk_user

            vk_channel = self._resolve_vk_channel_name(user_data)
            if vk_channel:
                channel_user = db.query(User).filter(
                    func.lower(User.vk_channel_name) == vk_channel.lower()
                ).first()
                if channel_user:
                    users_by_id[channel_user.id] = channel_user

        return list(users_by_id.values())

    def _merge_users_into_target(self, target_user: User, source_users: List[User], db: Session) -> None:
        """Merge all conflicting users into the resolved target account."""
        seen_user_ids = {target_user.id}
        for source_user in source_users:
            if not source_user or source_user.id in seen_user_ids:
                continue
            seen_user_ids.add(source_user.id)
            session_manager._merge_user_accounts(source_user.id, target_user.id, db, commit=False)

    def _create_user_shell(self, db: Session) -> User:
        """Create a new empty user record for a first-time OAuth login."""
        user = User(role="user", is_active=True)
        db.add(user)
        db.flush()
        logger.info("[OAUTH] Created new user shell %s", user.id)
        return user

    def _upsert_platform_token(
        self,
        db: Session,
        user: User,
        platform: str,
        user_data: OAuthUserData,
    ) -> bool:
        """Create or refresh a platform token within the current transaction."""
        encrypted_access_token = encrypt_token(user_data.access_token)
        encrypted_refresh_token = encrypt_token(user_data.refresh_token) if user_data.refresh_token else None

        token_record = db.query(UserToken).filter(
            UserToken.user_id == user.id,
            UserToken.platform == platform,
        ).first()
        token_existed = token_record is not None

        if token_record is None:
            token_record = db.query(UserToken).filter(
                UserToken.platform == platform,
                UserToken.platform_user_id == user_data.platform_user_id,
            ).first()
            if token_record and token_record.user_id != user.id:
                token_record.user_id = user.id
                token_existed = True

        if token_record is None:
            token_record = UserToken(
                user_id=user.id,
                platform=platform,
                platform_user_id=user_data.platform_user_id,
                avatar_url=user_data.avatar_url,
                access_token=encrypted_access_token,
                refresh_token=encrypted_refresh_token,
                expires_at=user_data.expires_at,
                scopes=user_data.scopes,
                auth_type="full",
                is_active=True,
            )
            db.add(token_record)
            logger.info("[OAUTH] Created %s token for user %s", platform, user.id)
            return False

        token_record.platform_user_id = user_data.platform_user_id
        token_record.avatar_url = user_data.avatar_url
        token_record.access_token = encrypted_access_token
        if encrypted_refresh_token is not None:
            token_record.refresh_token = encrypted_refresh_token
        token_record.expires_at = user_data.expires_at
        token_record.scopes = user_data.scopes
        token_record.auth_type = "full"
        token_record.is_active = True
        logger.info("[OAUTH] Updated %s token for user %s", platform, user.id)
        return token_existed

    def _apply_platform_profile(self, user: User, platform: str, user_data: OAuthUserData) -> None:
        """Persist platform-specific profile fields on the unified user."""
        if platform == Platform.TWITCH and user_data.username:
            user.twitch_username = user_data.username
        elif platform == Platform.VK:
            self._apply_vk_profile(user, user_data)

    def _configured_admin_entries(self) -> set[tuple[str, str]]:
        """Return configured platform identities that should become app admins."""
        entries: set[tuple[str, str]] = set()
        for raw_entry in (settings.admin_users or "").split(","):
            entry = raw_entry.strip()
            if not entry or ":" not in entry:
                continue
            platform, value = entry.split(":", 1)
            platform = platform.strip().lower()
            value = value.strip().lower()
            if platform and value:
                entries.add((platform, value))
        return entries

    def _is_configured_admin_identity(self, platform: str, user_data: OAuthUserData) -> bool:
        """Check whether OAuth identity matches the configured admin allowlist."""
        normalized_platform = str(platform).lower()
        values = {
            str(user_data.platform_user_id or "").strip().lower(),
            str(user_data.username or "").strip().lower(),
            str(user_data.channel_name or "").strip().lower(),
        }
        values.discard("")

        return any(
            entry_platform == normalized_platform and entry_value in values
            for entry_platform, entry_value in self._configured_admin_entries()
        )

    def _apply_admin_bootstrap(self, user: User, platform: str, user_data: OAuthUserData) -> None:
        """Promote configured OAuth identities to app admin during login."""
        if not self._is_configured_admin_identity(platform, user_data):
            return

        if user.role != "admin" or not user.is_admin:
            logger.warning(
                "[ADMIN BOOTSTRAP] Promoting user %s via %s:%s",
                user.id,
                platform,
                user_data.platform_user_id,
            )
        user.role = "admin"
        user.is_admin = True

    async def handle_oauth_callback(
        self,
        request: Request,
        db: Session,
        platform: str,
        user_data: OAuthUserData,
        current_user: Optional[Dict] = None,
        auto_connect_bot: bool = True
    ) -> OAuthResult:
        """
        Handle an OAuth callback for any supported platform.

        Args:
            request: FastAPI request object.
            db: Database session.
            platform: Platform name, for example twitch or vk.
            user_data: User data returned by the OAuth provider.
            current_user: Current authenticated user during account linking.
            auto_connect_bot: Whether to auto-connect the bot after authorization.

        Returns:
            OAuthResult with the resolved user and redirect metadata.
        """
        try:
            is_linking = current_user is not None
            session_id = request.cookies.get('session_id')
            logger.info("[OAUTH START] session_id from cookie: %s", mask_session_id(session_id))

            monitored_channel = self._get_monitored_channel(platform, user_data)
            active_session = self._get_active_session_for_channel(db, monitored_channel)
            active_session_user = None
            if active_session:
                active_session_user = db.query(User).filter(User.id == active_session.user_id).first()
                logger.info(
                    "[OAUTH] Active session %s found for %s (user=%s)",
                    mask_session_id(active_session.session_id),
                    monitored_channel,
                    active_session.user_id,
                )

            current_authenticated_user = None
            if is_linking:
                current_authenticated_user = db.query(User).filter(User.id == current_user["id"]).first()
                if not current_authenticated_user:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=ErrorMessages.USER_NOT_FOUND
                    )

            identity_matches = self._find_identity_matches(db, platform, user_data)
            logger.info(
                "[OAUTH] Identity matches for %s:%s -> %s",
                platform,
                user_data.platform_user_id,
                [user.id for user in identity_matches],
            )

            unified_user = current_authenticated_user or active_session_user or (identity_matches[0] if identity_matches else None)
            if unified_user is None:
                logger.info("[OAUTH] No unified user found, creating a new account shell")
                unified_user = self._create_user_shell(db)
            else:
                logger.info("[OAUTH] Using unified user %s for %s callback", unified_user.id, platform)

            merge_candidates: List[User] = []
            if active_session_user and active_session_user.id != unified_user.id:
                merge_candidates.append(active_session_user)
            merge_candidates.extend(identity_matches)
            self._merge_users_into_target(unified_user, merge_candidates, db)

            if not is_linking:
                logger.info("[SECURITY] Fresh login for user %s via %s", unified_user.id, platform)
                self._deactivate_other_platform_tokens(unified_user.id, platform, db)
            else:
                logger.info("[LINK] Linking %s to existing user %s", platform, unified_user.id)

            self._upsert_platform_token(db, unified_user, platform, user_data)
            self._apply_platform_profile(unified_user, platform, user_data)
            self._apply_admin_bootstrap(unified_user, platform, user_data)
            unified_user.is_active = True
            db.flush()

            from core.token_validation_cache import token_validation_cache
            token_validation_cache.invalidate(unified_user.id, platform)
            logger.info(f"[CACHE] Token validation cache invalidated for user {unified_user.id}, platform {platform}")

            db.commit()
            logger.info(f"User {unified_user.id} updated with {platform} username: {getattr(unified_user, f'{platform}_username', 'None')}")

            is_new_session = False

            if not is_linking:
                is_new_session = True
                device_info = {
                    "user_agent": request.headers.get("user-agent"),
                    "ip": getattr(request.client, 'host', 'unknown'),
                    "monitored_channel": monitored_channel,
                    "platform": platform
                }
                logger.info("[OAUTH] Creating session for user %s with device_info=%s", unified_user.id, device_info)
                session_id = session_manager.create_session(
                    user_id=unified_user.id,
                    device_info=device_info
                )
                logger.info("[OK] New session created: %s", mask_session_id(session_id))

                try:
                    from core.connection_manager import get_connection_manager
                    connection_manager = get_connection_manager()
                    if platform == "vk":
                        channel_identifier = self._resolve_vk_channel_name(user_data) or user_data.platform_user_id
                    else:
                        channel_identifier = user_data.username if user_data.username else user_data.platform_user_id
                    connection_manager.add_active_session(channel_identifier, session_id)
                except Exception as e:
                    logger.error(f"Error notifying connection_manager about new session: {e}")

                await self._setup_user_channel_settings(db, unified_user.id, platform, user_data)

            if is_linking:
                await self._setup_user_channel_settings(db, unified_user.id, platform, user_data)

            if auto_connect_bot:
                logger.info(f"[AUTO-CONNECT] Starting auto-connect bot for platform={platform}")
                if platform == "vk":
                    channel_identifier = self._resolve_vk_channel_name(user_data) or user_data.platform_user_id
                else:
                    channel_identifier = user_data.username if user_data.username else user_data.platform_user_id
                logger.info(f"[AUTO-CONNECT] Channel identifier: {channel_identifier}")
                await self._auto_connect_bot(platform, channel_identifier)
                logger.info(f"[AUTO-CONNECT] Auto-connect completed for {platform}:{channel_identifier}")
            else:
                logger.info(f"[INFO] Auto-connect disabled for {platform}")

            redirect_url = self._get_redirect_url(platform, is_linking, is_new_session)

            return OAuthResult(
                user=unified_user,
                session_id=session_id,
                is_new_session=is_new_session,
                redirect_url=redirect_url
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"{platform.title()} auth error: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Internal server error during {platform} authentication"
            )

    def create_oauth_response(self, oauth_result: OAuthResult) -> RedirectResponse:
        """
        Build the redirect response and attach the session cookies.

        Args:
            oauth_result: OAuth authorization result.

        Returns:
            RedirectResponse with cookies applied.
        """
        response = RedirectResponse(url=oauth_result.redirect_url)

        if oauth_result.session_id:
            cookie_settings = get_session_cookie_settings(oauth_result.session_id)
            response.set_cookie(**cookie_settings)

        return response


    def _get_redirect_url(self, platform: str, is_linking: bool, is_new_session: bool) -> str:
        """Resolve the frontend redirect URL for the current auth flow."""
        if is_linking:
            return f"{FRONTEND_REDIRECTS['settings']}?auth_link={platform}&success=1"
        else:
            return f"{FRONTEND_REDIRECTS['dashboard']}?auth={platform}&success=1"

    async def _auto_connect_bot(self, platform: str, channel_name: str) -> None:
        """
        Automatically connect the bot to the channel after authorization.

        Args:
            platform: Platform name.
            channel_name: Channel identifier.
        """
        try:
            from core.connection_manager import get_connection_manager
            connection_manager = get_connection_manager()

            logger.info(f"[BOT] Attempting auto-connect for {platform} bot to channel {channel_name}")
            has_sessions = connection_manager.is_channel_active(channel_name)
            logger.info(f"[BOT] Active sessions for {channel_name}: {has_sessions}")

            if platform == Platform.TWITCH:
                logger.info(f"[BOT] Connecting Twitch bot to {channel_name}")
                await self._connect_twitch_bot(channel_name)
            elif platform == Platform.VK:
                logger.info(f"[BOT] Connecting VK Live bot to {channel_name}")
                await self._connect_vk_bot(channel_name)
            else:
                logger.info(f"[BOT] No bot auto-connect flow is defined for platform: {platform}")

        except Exception as e:
            logger.error(f"[ERROR] Error auto-connecting {platform} bot to {channel_name}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")

    async def _connect_twitch_bot(self, channel_name: str) -> None:
        """Connect the Twitch bot after OAuth authorization."""
        try:
            from startup.bot_registry import get_bot_registry
            bot_instance = get_bot_registry().twitch_bot

            if bot_instance:
                logger.info(f"[BOT] Bot instance exists, attempting to join channel: {channel_name}")
                success = await bot_instance.join_channel(channel_name)
                if success:
                    logger.info(f"[OK] Twitch bot successfully connected to {channel_name} via OAuth")

                    import asyncio
                    await asyncio.sleep(2)
                    await bot_instance.send_welcome_message(channel_name)
                else:
                    logger.warning(f"[ERROR] Failed to connect Twitch bot to {channel_name} via OAuth")
            else:
                logger.error("[ERROR] Twitch bot instance not found. Bot was not created at startup.")

        except Exception as e:
            logger.error(f"[ERROR] Error connecting Twitch bot during OAuth: {e}")

    async def _connect_vk_bot(self, channel_name: str) -> None:
        """Connect the VK Live bot to the user channel after OAuth."""
        try:
            from core.connection_manager import get_connection_manager
            from core.database import get_db
            from startup.bot_initializer import initialize_vk_bot
            from startup.bot_registry import get_bot_registry

            registry = get_bot_registry()
            bot_instance = registry.vk_bot

            if not bot_instance:
                db = next(get_db())
                try:
                    connection_manager = get_connection_manager()
                    vk_channels = await connection_manager.get_vk_channels_for_bot(db)
                finally:
                    db.close()

                started = await initialize_vk_bot(vk_channels)
                if not started:
                    logger.error("[ERROR] VK Live bot is not started (bot OAuth token is likely missing)")
                    return

                bot_instance = get_bot_registry().vk_bot
                if not bot_instance:
                    logger.error("[ERROR] VK Live bot instance still missing after initialization")
                    return

            logger.info(f"[BOT] VK bot instance exists, attempting to connect to channel: {channel_name}")
            success = await bot_instance.connect_to_channel(channel_name)

            if success:
                logger.info(f"[OK] VK Live bot successfully connected to {channel_name} via OAuth")
            else:
                logger.warning(f"[ERROR] Failed to connect VK Live bot to {channel_name} via OAuth")

        except Exception as e:
            logger.error(f"Error connecting VK Live bot: {e}")

    async def _setup_user_channel_settings(self, db: Session, user_id: int, platform: str, user_data: OAuthUserData) -> None:
        """Store channel settings in UserSettings for automatic bot connection."""
        try:
            from core.database import UserSettings

            settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
            if not settings:
                settings = UserSettings(
                    user_id=user_id,
                    chat_enabled=True
                )
                db.add(settings)
                db.flush()

            if platform == "twitch":
                channel_name = user_data.username.lower()
                settings.channel_name = channel_name
                logger.info(f"[OK] Set Twitch channel_name: {channel_name}")
            elif platform == "vk":
                channel_name = self._resolve_vk_channel_name(user_data)
                if channel_name:
                    settings.vk_channel_name = channel_name.lower()
                    logger.info(f"[OK] Set VK channel_name: {channel_name}")
                else:
                    settings.vk_channel_name = None
                    logger.info("[OK] Cleared VK channel_name in UserSettings (no channel slug)")

            db.commit()
            logger.info(f"[OK] UserSettings updated for user {user_id}, platform {platform}")

        except Exception as e:
            logger.error(f"Error setting up user channel settings: {e}")
            db.rollback()

oauth_handler = OAuthHandler()
