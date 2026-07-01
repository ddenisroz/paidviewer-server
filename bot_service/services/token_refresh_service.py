# bot_service/services/token_refresh_service.py
"""
Service for automatic platform-token refresh.
"""
import logging
import httpx
import aiohttp
import base64
from datetime import timedelta
from typing import Optional, Callable, Awaitable, List
from sqlalchemy.orm import Session

from core.database import get_db, UserToken
from core.datetime_utils import utcnow_naive
from core.token_encryption import encrypt_token, decrypt_token
from core.retry_utils import retry_async
from core.config import settings
from repositories.user_token_repository import UserTokenRepository

logger = logging.getLogger('token_refresh')

# Type aliases for platform refresh handlers.
RefreshHandler = Callable[[UserToken, Session], Awaitable[bool]]


class TokenRefreshService:
    """Service for refreshing access tokens via refresh tokens."""
    
    _refresh_handlers: dict[str, RefreshHandler] = {}
    
    def __init__(self):
        # Register platform-specific refresh handlers.
        self._refresh_handlers = {
            'twitch': self._refresh_twitch,
            'vk': self._refresh_vk,
            'donationalerts': self._refresh_donationalerts
        }
        
    def _get_refresh_handler(self, platform: str) -> Optional[RefreshHandler]:
        """Get the refresh handler for a platform."""
        return self._refresh_handlers.get(platform)

    async def refresh_if_needed(self, user_id: int, platform: str, db: Optional[Session] = None) -> bool:
        if db:
             repo = UserTokenRepository(db)
             token = repo.get_by_user_and_platform(user_id, platform)
             if not token: return False
             if token.expires_at and token.expires_at > utcnow_naive() + timedelta(days=7):
                 return True
             return await self._refresh_token(token, db)
             
        # No DB, create one
        for session in get_db():
             repo = UserTokenRepository(session)
             token = repo.get_by_user_and_platform(user_id, platform)
             if not token: return False
             if token.expires_at and token.expires_at > utcnow_naive() + timedelta(days=7):
                 return True
             return await self._refresh_token(token, session)
        return False

    async def refresh_on_401(self, user_id: int, platform: str, db: Optional[Session] = None) -> bool:
        """Refresh a token after receiving a 401 response."""
        logger.info(f"Got 401 for {platform} user {user_id}, attempting refresh...")
        
        if db:
            repo = UserTokenRepository(db)
            token = repo.get_by_user_and_platform(user_id, platform)
            if not token: return False
            return await self._refresh_token(token, db)
            
        for session in get_db():
            repo = UserTokenRepository(session)
            token = repo.get_by_user_and_platform(user_id, platform)
            if not token: return False
            return await self._refresh_token(token, session)
        return False

    async def _refresh_token(self, token: UserToken, db: Session) -> bool:
        """Refresh a token using the registered refresh-token handler."""
        handler = self._get_refresh_handler(token.platform)
        if not handler:
            logger.error(f"No refresh handler for platform {token.platform}")
            return False
            
        try:
            return await handler(token, db)
        except Exception:
            logger.exception("Error refreshing {token.platform} token")
            return False

    async def _make_refresh_request(self, url: str, data: dict, headers: dict = None) -> Optional[dict]:
        """Shared helper for refresh requests with retry handling."""
        async def _do_refresh():
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, data=data, headers=headers)
                response.raise_for_status()
                return response.json()

        try:
            return await retry_async(_do_refresh, max_attempts=3, initial_delay=1.0)
        except Exception:
            logger.exception("Refresh request failed")
            return None

    def _update_token_from_response(self, token: UserToken, data: dict, db: Session) -> None:
        """Update a database token row from an OAuth refresh response."""
        repo = UserTokenRepository(db)
        
        refresh_token = data.get('refresh_token')
        access_token = data.get('access_token')
        expires_in = data.get('expires_in')
        
        # Calculate expiry
        expires_at = None
        if expires_in:
             expires_at = utcnow_naive() + timedelta(seconds=int(expires_in))
        
        # Use upsert or manual update. Since we have the object attached to session:
        # We can just update fields.
        if access_token:
            token.access_token = encrypt_token(access_token)
        if refresh_token:
            token.refresh_token = encrypt_token(refresh_token)
        if expires_at:
            token.expires_at = expires_at
        
        token.updated_at = utcnow_naive()
        db.commit() # Repository 'save' or just commit
        # repo.save(token) would be cleaner but token is already attached.
        # Let's prefer explicit commit here as existing service logic did.

    async def _refresh_twitch(self, token: UserToken, db: Session) -> bool:
        """Refresh a Twitch token."""
        refresh_token = decrypt_token(token.refresh_token)
        if not refresh_token:
            return False

        data = await self._make_refresh_request(
            "https://id.twitch.tv/oauth2/token",
            {
                'client_id': settings.twitch_client_id,
                'client_secret': settings.twitch_client_secret,
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token
            }
        )
        
        if data:
            self._update_token_from_response(token, data, db)
            logger.info(f"Twitch token refreshed for user {token.user_id}")
            return True
        return False

    async def _refresh_vk(self, token: UserToken, db: Session) -> bool:
        """Refresh a VK Live token."""
        refresh_token = decrypt_token(token.refresh_token)
        if not refresh_token:
            return False
            
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'client_id': settings.vk_client_id,
            'client_secret': settings.vk_client_secret
        }
        
        data = await self._make_refresh_request(
             'https://api.live.vkvideo.ru/oauth/server/token',
             data,
             headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )
        
        if data:
            self._update_token_from_response(token, data, db)
            logger.info(f"VK token refreshed for user {token.user_id}")
            return True
        return False
        
    async def _refresh_donationalerts(self, token: UserToken, db: Session) -> bool:
        """Refresh a DonationAlerts token."""
        refresh_token = decrypt_token(token.refresh_token)
        if not refresh_token:
            return False

        data = await self._make_refresh_request(
            "https://www.donationalerts.com/oauth/token",
            {
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token,
                'client_id': settings.donationalerts_client_id,
                'client_secret': settings.donationalerts_client_secret,
            }
        )
        
        if data:
            self._update_token_from_response(token, data, db)
            return True
        return False

# Shared module-level service instance.
token_refresh_service = TokenRefreshService()

