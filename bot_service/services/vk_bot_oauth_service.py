# bot_service/services/vk_bot_oauth_service.py
"""Service for managing the VK Live bot OAuth token with auto-refresh support."""

import logging
import httpx
import base64
from datetime import timedelta
from typing import Optional, Dict, Any
from sqlalchemy import or_
from sqlalchemy.orm import Session

from core.config import settings
from core.database import db_session, User, UserToken
from models.bot_token import BotToken
from core.token_encryption import encrypt_token, decrypt_token
from core.datetime_utils import utcnow_naive
from repositories.bot_token_repository import BotTokenRepository

logger = logging.getLogger(__name__)


def _current_settings():
    """Return the live settings object instead of a stale import captured before tests reload config."""
    from core.config import settings as live_settings

    return live_settings


class VkBotOAuthService:
    """Service for VK Live bot OAuth authorization with refresh-token support."""
    REFRESH_IF_NEEDED_THRESHOLD_SECONDS = 15 * 60
    
    # Bot scopes required by the VK runtime.
    BOT_SCOPES = [
        'channel:stream:settings',
        'channel:points:rewards',
        'channel:points:rewards:demands',
        'chat:message:send',
    ]
    
    @staticmethod
    def get_authorization_url(state: str) -> str:
        """Build the VK Live bot OAuth authorization URL."""
        import urllib.parse
        app_settings = _current_settings()
        
        scopes = ','.join(VkBotOAuthService.BOT_SCOPES)
        redirect_uri = app_settings.vk_bot_redirect_uri
        
        params = {
            "client_id": app_settings.vk_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scopes,
            "state": state
        }
        
        query_string = urllib.parse.urlencode(params)
        
        auth_url = f"https://auth.live.vkvideo.ru/app/oauth2/authorize?{query_string}"
        
        return auth_url
    
    @staticmethod
    async def exchange_code_for_token(code: str) -> Dict[str, Any]:
        """Exchange an authorization code for access and refresh tokens."""
        app_settings = _current_settings()
        if not all([app_settings.vk_client_id, app_settings.vk_client_secret]):
            raise ValueError("VK credentials not configured")
        
        redirect_uri = app_settings.vk_bot_redirect_uri
        
        # Basic Auth
        credentials = f"{app_settings.vk_client_id}:{app_settings.vk_client_secret}"
        base64_credentials = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {base64_credentials}"
        }

        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            response = await client.post(
                "https://api.live.vkvideo.ru/oauth/server/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri
                },
                headers=headers
            )
            
            if response.status_code != 200:
                error_body = response.text
                logger.error(f"Failed to exchange code for token: {error_body}")
                raise Exception(f"Token exchange failed: {error_body}")
            
            data = response.json()
            
            logger.info("[OK] [VK BOT OAUTH] Successfully exchanged code for tokens")
            logger.info(f"[INFO] Token expires in: {data.get('expires_in')} seconds")
            
            return data
    
    @staticmethod
    async def get_bot_user_info(access_token: str) -> Dict[str, Any]:
        """Fetch bot account information from the VK API."""
        async with httpx.AsyncClient(timeout=10.0, verify=True) as client:
            # Try Prod API first; dev is an explicit fallback.
            try:
                 response = await client.get(
                      "https://api.live.vkvideo.ru/v1/current_user",
                      headers={"Authorization": f"Bearer {access_token}"}
                 )
                 if response.status_code == 200:
                      data = response.json()
                      user = data.get("data", {}).get("user", {})
                      return {
                           'id': str(user.get('id')),
                           'login': user.get('nick'),
                           'display_name': user.get('nick')
                      }
            except Exception as e:
                 logger.exception("Prod API check failed")

            # Try Dev API fallback
            try:
                 response = await client.get(
                      "https://apidev.live.vkvideo.ru/v1/current_user",
                      headers={"Authorization": f"Bearer {access_token}"}
                 )
                 if response.status_code == 200:
                      data = response.json()
                      user = data.get("data", {}).get("user", {})
                      return {
                           'id': str(user.get('id')),
                           'login': user.get('nick'),
                           'display_name': user.get('nick')
                      }
            except Exception as e:
                 logger.exception("Dev API fallback failed")

            raise Exception("Failed to get VK user info")
    
    @staticmethod
    async def save_bot_token(
        access_token: str,
        refresh_token: str,
        expires_in: int,
        scopes: list,
        bot_user_id: str,
        bot_login: str,
        db: Optional[Session] = None
    ) -> bool:
        """Persist the bot token in the database."""
        def _save(session_db: Session) -> bool:
            try:
                repo = BotTokenRepository(session_db)
                # Reuse an existing VK bot token row when available.
                bot_token = repo.get_by_platform('vk')
                
                expires_at = utcnow_naive() + timedelta(seconds=expires_in)
                
                if bot_token:
                    # Update the existing row.
                    bot_token.access_token = encrypt_token(access_token)
                    if refresh_token:
                        bot_token.refresh_token = encrypt_token(refresh_token)
                    bot_token.expires_at = expires_at
                    bot_token.scopes = scopes
                    bot_token.bot_user_id = bot_user_id
                    bot_token.bot_login = bot_login
                    bot_token.updated_at = utcnow_naive()
                    logger.info(f"[UPDATE] Updated VK bot token for {bot_login}")
                else:
                    # Create a new row.
                    bot_token = BotToken(
                        platform='vk',
                        access_token=encrypt_token(access_token),
                        refresh_token=encrypt_token(refresh_token) if refresh_token else None,
                        expires_at=expires_at,
                        scopes=scopes,
                        bot_user_id=bot_user_id,
                        bot_login=bot_login
                    )
                    logger.info(f"[CREATE] Created VK bot token for {bot_login}")
                
                repo.save(bot_token)
                return True
                
            except Exception as e:
                logger.exception("Error saving VK bot token")
                session_db.rollback()
                return False
        
        if db is not None:
            return _save(db)
        
        with db_session() as new_db:
            return _save(new_db)
    
    @staticmethod
    async def get_bot_token(db: Optional[Session] = None) -> Optional[Dict[str, Any]]:
        """Load the bot token from the database."""
        async def _get(session_db: Session) -> Optional[Dict[str, Any]]:
            repo = BotTokenRepository(session_db)
            bot_token = repo.get_by_platform('vk')

            if not bot_token and settings.bot_token_auto_bootstrap_enabled:
                logger.warning(
                    "[BOOTSTRAP] VK bot token not found in bot_tokens; trying auto-bootstrap from user OAuth tokens"
                )
                if await VkBotOAuthService._bootstrap_from_user_tokens(session_db):
                    bot_token = repo.get_by_platform('vk')

            if not bot_token:
                return None

            return {
                'access_token': decrypt_token(bot_token.access_token),
                'refresh_token': decrypt_token(bot_token.refresh_token) if bot_token.refresh_token else None,
                'expires_at': bot_token.expires_at,
                'scopes': bot_token.scopes if isinstance(bot_token.scopes, list) else [],
                'bot_login': bot_token.bot_login,
                'bot_user_id': bot_token.bot_user_id
            }

        if db is not None:
            return await _get(db)

        with db_session() as new_db:
            return await _get(new_db)

    @staticmethod
    async def _bootstrap_from_user_tokens(session_db: Session) -> bool:
        """
        Self-healing fallback:
        if dedicated VK bot token is missing, seed it from existing OAuth user token.
        """
        query = (
            session_db.query(UserToken)
            .join(User, User.id == UserToken.user_id)
            .filter(
                UserToken.platform == 'vk',
                UserToken.is_active.is_(True),
                UserToken.access_token.isnot(None),
                User.is_active.is_(True),
                User.is_blocked.is_(False),
            )
        )

        if settings.bot_token_auto_bootstrap_admin_only:
            query = query.filter(or_(User.role == 'admin', User.is_admin.is_(True)))

        if settings.bot_token_auto_bootstrap_require_refresh_token:
            query = query.filter(UserToken.refresh_token.isnot(None))

        candidates = query.order_by(UserToken.updated_at.desc()).all()
        if not candidates:
            logger.warning("[BOOTSTRAP] No eligible VK user OAuth tokens found")
            return False

        now = utcnow_naive()
        for candidate in candidates:
            access_token = decrypt_token(candidate.access_token) if candidate.access_token else None
            refresh_token = decrypt_token(candidate.refresh_token) if candidate.refresh_token else None
            if not access_token:
                continue
            if settings.bot_token_auto_bootstrap_require_refresh_token and not refresh_token:
                continue

            expires_in = 30 * 24 * 3600
            if candidate.expires_at:
                seconds_left = int((candidate.expires_at - now).total_seconds())
                if seconds_left <= 60:
                    continue
                expires_in = seconds_left

            try:
                user_info = await VkBotOAuthService.get_bot_user_info(access_token)
            except Exception as e:
                logger.warning(
                    "[BOOTSTRAP] Failed to validate VK user token for user_id=%s: %s",
                    candidate.user_id,
                    e,
                )
                continue

            saved = await VkBotOAuthService.save_bot_token(
                access_token=access_token,
                refresh_token=refresh_token or "",
                expires_in=expires_in,
                scopes=candidate.scopes if isinstance(candidate.scopes, list) else [],
                bot_user_id=str(user_info.get('id') or candidate.platform_user_id or ""),
                bot_login=user_info.get('login') or "",
                db=session_db,
            )
            if saved:
                logger.warning(
                    "[BOOTSTRAP] VK bot token auto-seeded from user token (user_id=%s, login=%s)",
                    candidate.user_id,
                    user_info.get('login') or "unknown",
                )
                return True

        logger.warning("[BOOTSTRAP] Failed to auto-seed VK bot token from user OAuth tokens")
        return False
    
    @staticmethod
    async def refresh_bot_token(db: Optional[Session] = None) -> bool:
        """Refresh the bot token using the stored refresh token."""
        async def _refresh(session_db: Session) -> bool:
            try:
                repo = BotTokenRepository(session_db)
                bot_token = repo.get_by_platform('vk')

                if not bot_token or not bot_token.refresh_token:
                    logger.error("[ERROR] No VK bot token or refresh token found")
                    return False

                refresh_token = decrypt_token(bot_token.refresh_token)

                logger.info("[REFRESH] Refreshing VK bot token...")

                credentials = f"{settings.vk_client_id}:{settings.vk_client_secret}"
                base64_credentials = base64.b64encode(credentials.encode()).decode()

                headers = {
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Authorization": f"Basic {base64_credentials}"
                }

                async with httpx.AsyncClient(timeout=15.0, trust_env=False) as client:
                    response = await client.post(
                        "https://api.live.vkvideo.ru/oauth/server/token",
                        data={
                            "grant_type": "refresh_token",
                            "refresh_token": refresh_token
                        },
                        headers=headers
                    )

                if response.status_code == 200:
                    data = response.json()

                    bot_token.access_token = encrypt_token(data["access_token"])
                    if data.get("refresh_token"):
                        bot_token.refresh_token = encrypt_token(data["refresh_token"])
                    bot_token.expires_at = utcnow_naive() + timedelta(seconds=data["expires_in"])
                    bot_token.updated_at = utcnow_naive()

                    repo.save(bot_token)

                    logger.info(f"[OK] VK bot token refreshed for {bot_token.bot_login}")
                    return True

                logger.error(f"[ERROR] Failed to refresh VK bot token: {response.status_code} - {response.text}")
                return False

            except Exception as e:
                logger.exception("Error refreshing VK bot token")
                session_db.rollback()
                return False

        if db is not None:
            return await _refresh(db)

        with db_session() as new_db:
            return await _refresh(new_db)
    
    @staticmethod
    async def refresh_if_needed(db: Optional[Session] = None) -> bool:
        """Refresh the bot token when it is close to expiry."""
        async def _check_and_refresh(session_db: Session) -> bool:
            repo = BotTokenRepository(session_db)
            bot_token = repo.get_by_platform('vk')
            
            if not bot_token:
                logger.warning("[WARN] No VK bot token found in database")
                return False
            
            if not bot_token.expires_at:
                logger.debug("[INFO] Bot token has no expiration date")
                return True
            
            seconds_left = int((bot_token.expires_at - utcnow_naive()).total_seconds())

            if seconds_left > VkBotOAuthService.REFRESH_IF_NEEDED_THRESHOLD_SECONDS:
                logger.debug(f"[INFO] VK Bot token valid for {seconds_left} more seconds")
                return True

            logger.info(f"[REFRESH] VK Bot token expires in {seconds_left} seconds, refreshing...")
            return await VkBotOAuthService.refresh_bot_token(session_db)
        
        try:
            if db is not None:
                return await _check_and_refresh(db)
            
            with db_session() as new_db:
                return await _check_and_refresh(new_db)
                
        except Exception as e:
            logger.exception("Error checking bot token expiration")
            return False


# Shared module-level instance.
vk_bot_oauth_service = VkBotOAuthService()

