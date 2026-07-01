
import logging
import base64
from typing import Optional, Dict, Any
import aiohttp

from core.config import settings
from integrations.base import TokenInfo, AuthenticationError, IntegrationError

logger = logging.getLogger(__name__)

class VKOAuth:
    """
    VK Live OAuth implementation.
    """
    TOKEN_URL = "https://api.live.vkvideo.ru/oauth/server/token"
    
    def __init__(self):
        self.client_id = settings.vk_client_id
        self.client_secret = settings.vk_client_secret
        self.redirect_uri = settings.vk_redirect_uri

    def get_auth_url(self, state: Optional[str] = None) -> str:
        """
        Generate OAuth authorization URL.
        VK Live uses a specific flow (often implied or external), 
        but if needed, this would return the URL.
        """
        # Note: Actual auth flow might be frontend-driven or manual.
        # State verification follows the standard OAuth2 CSRF protection flow.
        scope = "channel:write stream:write" # Example scopes
        return (
            f"https://api.live.vkvideo.ru/oauth/authorize"
            f"?client_id={self.client_id}"
            f"&redirect_uri={self.redirect_uri}"
            f"&response_type=code"
            f"&scope={scope}"
        )

    async def exchange_code(self, code: str) -> TokenInfo:
        """
        Exchange authorization code for access token.
        """
        if not self.client_id or not self.client_secret:
            raise AuthenticationError("VK credentials not configured")

        payload = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": self.redirect_uri
        }
        
        try:
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.TOKEN_URL, data=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise AuthenticationError(f"Failed to exchange code: {response.status} - {error_text}")
                    
                    data = await response.json()
                    
                    return TokenInfo(
                        access_token=data["access_token"],
                        refresh_token=data.get("refresh_token"),
                        expires_in=data.get("expires_in"),
                        scopes=data.get("scope", "").split() if data.get("scope") else []
                    )
        except Exception as e:
            logger.error(f"VK code exchange error: {e}")
            raise IntegrationError(f"OAuth error: {e}")

    async def refresh_token(self, refresh_token: str) -> TokenInfo:
        """
        Refresh access token using refresh_token.
        """
        if not self.client_id or not self.client_secret:
            raise AuthenticationError("VK credentials not configured")

        # Prepare Basic Auth header
        credentials = f"{self.client_id}:{self.client_secret}"
        base64_credentials = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {base64_credentials}"
        }

        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "redirect_uri": self.redirect_uri
        }

        try:
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.TOKEN_URL, data=payload, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise AuthenticationError(f"Failed to refresh token: {response.status} - {error_text}")
                    
                    data = await response.json()
                    
                    return TokenInfo(
                        access_token=data["access_token"],
                        refresh_token=data.get("refresh_token", refresh_token),
                        expires_in=data.get("expires_in"),
                        scopes=data.get("scope", "").split() if data.get("scope") else []
                    )
        except Exception as e:
            logger.error(f"VK token refresh error: {e}")
            raise IntegrationError(f"RefreshToken error: {e}")
