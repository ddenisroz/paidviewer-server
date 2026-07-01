"""
VK API Authentication Module
Handles token management, refresh, and user info retrieval.
"""
import base64
import logging
from typing import Optional, Dict, Any, cast

import aiohttp

from core.token_manager import token_manager
from core.token_utils import get_user_token_from_db
from core.session_manager import session_manager
from core.config import settings
from .vk_base import VKBase, VK_API_TIMEOUT

logger = logging.getLogger(__name__)

class VKAuth(VKBase):
    """
    Authentication methods for VK Live API.
    Handles token retrieval, validation, and refreshing.
    """

    
    # Cache for Service Token (Client Credentials)
    _service_token: Optional[str] = None
    _service_token_expires: float = 0

    async def _get_service_token(self) -> Optional[str]:
        """
        Get Service Token (Client Credentials) for app-level requests (like search).
        """
        import time
        from core.config import settings

        current_time = time.time()
        # Return cached if valid (with 60s buffer)
        if self._service_token and current_time < (self._service_token_expires - 60):
            return self._service_token

        try:
            client_id = settings.vk_client_id
            client_secret = settings.vk_client_secret
            
            if not client_id or not client_secret:
                logger.error("[VK AUTH] Client ID or Secret missing for Service Token")
                return None

            import base64
            credentials = f"{client_id}:{client_secret}"
            base64_credentials = base64.b64encode(credentials.encode()).decode()

            full_url = "https://api.live.vkvideo.ru/oauth/server/token"
            
            headers = {
                "Authorization": f"Basic {base64_credentials}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            data = {
                "grant_type": "client_credentials"
            }
            
            async with aiohttp.ClientSession(timeout=VK_API_TIMEOUT) as session:
                # Use default SSL verification for Prod Auth
                async with session.post(full_url, data=data, headers=headers) as response:
                    if response.status == 200:
                        token_data = await response.json()
                        access_token = token_data.get("access_token")
                        expires_in = token_data.get("expires_in", 3600)
                        
                        if access_token:
                            self._service_token = access_token
                            self._service_token_expires = current_time + expires_in
                            logger.info(f"[VK AUTH] Generated Service Token (expires in {expires_in}s)")
                            return access_token
                    else:
                        text = await response.text()
                        logger.error(f"[VK AUTH] Failed to get Service Token: {response.status} - {text}")
                        return None
        except Exception:
             logger.exception("[VK AUTH] Error getting Service Token")
             return None

    def _get_user_token(self, user_id: str, session_id: Optional[str] = None) -> Optional[str]:
        """
        Get VK user token via TokenManager.
        
        Args:
            user_id: User ID (int or str)
            session_id: Session ID (optional) for enhanced security check
        
        Returns:
            Access token string or None
        """
        try:
            # UNIFIED: Use TokenManager for consistent token retrieval
            user_id_int = int(user_id) if isinstance(user_id, str) else user_id
            return cast(Optional[str], token_manager.get_user_token(
                user_id=user_id_int,
                platform="vk",
                session_id=session_id,
                require_session_check=session_id is not None
            ))
        except Exception:
            logger.exception("Error getting VK token for user %s", user_id)
            return None

    async def _refresh_user_token(self, user_id: int) -> Optional[str]:
        """
        Refresh VK user token using refresh_token.
        Updates the database and TokenValidationCache.
        """
        try:
            tokens = get_user_token_from_db(user_id, "vk")
            if not tokens or not tokens.get("refresh_token"):
                logger.warning(f"No refresh token found for user {user_id}")
                return None

            refresh_token = tokens["refresh_token"]
            client_id = settings.vk_client_id
            client_secret = settings.vk_client_secret

            if not all([client_id, client_secret]):
                logger.error("VK credentials not configured for token refresh")
                return None

            # Prepare Basic Auth header
            credentials = f"{client_id}:{client_secret}"
            base64_credentials = base64.b64encode(credentials.encode()).decode()

            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {base64_credentials}"
            }

            payload = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "redirect_uri": settings.vk_redirect_uri
            }

            # Use SSL context from base class if needed (for dev) or default
            # Implementation decides whether to pass ssl=self.ssl_context
            # Original code disabled verification globally via urllib3 but passed nothing to aiohttp?
            # Original code: `async with aiohttp.ClientSession(timeout=VK_API_TIMEOUT) as session:`
            # But `VKLiveAPI.__init__` created `self.ssl_context` which wasn't used in `_refresh_user_token` in original file?
            # Let's check original file again... logic mostly relied on urllib3 hack for synchronous or just luck.
            # Ideally we pass ssl=False or ssl=context for aiohttp.
            # Since this is an external API (api.live.vkvideo.ru, NOT apidev), we should verify SSL!
            # The dev API is apidev.live.vkvideo.ru. 
            # The Auth endpoint is https://api.live.vkvideo.ru/oauth/server/token (Production URL?)
            
            # Let's assume standard SSL for auth unless it fails.
            
            async with aiohttp.ClientSession(timeout=VK_API_TIMEOUT) as session:
                async with session.post(
                    "https://api.live.vkvideo.ru/oauth/server/token",
                    data=payload,
                    headers=headers
                ) as response:
                    if response.status == 200:
                        token_data = await response.json()
                        new_access_token = token_data["access_token"]
                        new_refresh_token = token_data.get("refresh_token", refresh_token)
                        expires_in = token_data.get("expires_in", 3600)

                        logger.info(f"[AUTH] [VK REFRESH] Token expires_in: {expires_in} seconds ({expires_in / 3600:.1f} hours)")

                        # Calculate expiry time
                        from core.datetime_utils import utcnow_naive
                        from datetime import timedelta
                        expires_at = utcnow_naive() + timedelta(seconds=expires_in)

                        session_manager.save_user_tokens(
                            user_id=user_id,
                            platform="vk",
                            platform_user_id=tokens.get("platform_user_id", ""),
                            avatar_url=tokens.get("avatar_url"),
                            access_token=new_access_token,
                            refresh_token=new_refresh_token,
                            expires_at=expires_at,
                            scopes=tokens.get("scopes", [])
                        )

                        # Invalidate cache
                        from core.token_validation_cache import token_validation_cache
                        token_validation_cache.invalidate(user_id, "vk")

                        logger.info(f"VK token refreshed for user {user_id}")
                        return str(new_access_token)
                    else:
                        error_text = await response.text()
                        logger.error(f"VK token refresh failed: {response.status} - {error_text}")
                        return None

        except Exception:
            logger.exception("Error refreshing VK token for user %s", user_id)
            return None

    async def _get_current_user_info(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Get info about current user (streamer) via VK Live API.
        Requires STREAMER token (OAuth), not BOT token.
        """
        await self.rate_limiter.wait()
        try:
            # Use self.ssl_context because this calls self.live_base_url (apidev)
            async with aiohttp.ClientSession(timeout=VK_API_TIMEOUT) as session:
                headers = {"Authorization": f"Bearer {token}"}
                url = f"{self.BASE_URL}/v1/current_user"
                
                async with session.get(url, headers=headers, ssl=self.ssl_context) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info("[OK] Successfully got VK Live user info")
                        if isinstance(data, dict) and "data" in data:
                            return cast(Dict[str, Any], data["data"])
                    elif response.status == 401:
                        logger.debug("[INFO] /v1/current_user returned 401. Expected if using bot token.")
                        return None
                    else:
                        logger.warning(f"Endpoint /v1/current_user returned {response.status}: {await response.text()}")
        except Exception:
            logger.exception("VK Live API /v1/current_user request failed")
        return None

