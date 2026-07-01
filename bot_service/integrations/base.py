# bot_service/integrations/base.py
"""
Base classes and utilities for integrations.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, TypeVar, Generic
from dataclasses import dataclass
from enum import Enum

import aiohttp
from aiohttp import ClientTimeout

logger = logging.getLogger(__name__)


class IntegrationError(Exception):
    """Base exception for integration errors."""
    
    def __init__(self, message: str, status_code: Optional[int] = None, 
                 original_error: Optional[Exception] = None):
        self.message = message
        self.status_code = status_code
        self.original_error = original_error
        super().__init__(message)


class TokenExpiredError(IntegrationError):
    """Exception raised for expired tokens."""
    pass


class RateLimitError(IntegrationError):
    """Exception raised when the rate limit is exceeded."""
    pass


class AuthenticationError(IntegrationError):
    """Exception raised for authentication failures."""
    pass


@dataclass
class TokenInfo:
    """Token information."""
    access_token: str
    refresh_token: Optional[str] = None
    expires_at: Optional[float] = None
    scopes: Optional[list] = None
    
    def is_expired(self) -> bool:
        """Check whether the token is expired."""
        if self.expires_at is None:
            return False
        import time
        return time.time() >= self.expires_at


T = TypeVar('T')


class BaseIntegrationClient(ABC, Generic[T]):
    """
    Base client for external-service integrations.
    
    Provides:
    - Retry logic
    - Shared error handling
    - Timeouts
    - Logging
    """
    
    DEFAULT_TIMEOUT = ClientTimeout(total=30, connect=10)
    MAX_RETRIES = 3
    
    def __init__(self, base_url: str, timeout: Optional[ClientTimeout] = None):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout or self.DEFAULT_TIMEOUT
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session
    
    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    @abstractmethod
    async def _get_headers(self, token: Optional[TokenInfo] = None) -> Dict[str, str]:
        """Return request headers."""
        pass
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        token: Optional[TokenInfo] = None,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
        data: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Execute an HTTP request with retry logic.
        
        Args:
            method: HTTP method
            endpoint: Endpoint path without base_url
            token: Token information
            params: Query parameters
            json_data: JSON body
            data: Form data
            
        Returns:
            API response as a dictionary
            
        Raises:
            IntegrationError: Raised for API failures
            TokenExpiredError: Raised for expired tokens
            RateLimitError: Raised for rate-limit errors
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = await self._get_headers(token)
        session = await self._get_session()
        
        last_error: Optional[Exception] = None
        
        for attempt in range(self.MAX_RETRIES):
            try:
                async with session.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json_data,
                    data=data,
                ) as response:
                    return await self._handle_response(response)
                    
            except aiohttp.ClientError as e:
                last_error = e
                logger.warning(
                    f"[INTEGRATION] {self.__class__.__name__} request failed "
                    f"(attempt {attempt + 1}/{self.MAX_RETRIES}): {e}"
                )
                if attempt < self.MAX_RETRIES - 1:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
        
        raise IntegrationError(
            f"Request failed after {self.MAX_RETRIES} attempts",
            original_error=last_error
        )
    
    async def _handle_response(self, response: aiohttp.ClientResponse) -> Dict[str, Any]:
        """Handle the API response."""
        if response.status == 200:
            return await response.json()
        elif response.status == 204:
            return {"success": True}
        elif response.status == 401:
            raise TokenExpiredError("Token expired or invalid", status_code=401)
        elif response.status == 429:
            raise RateLimitError("Rate limit exceeded", status_code=429)
        elif response.status == 403:
            text = await response.text()
            raise AuthenticationError(f"Access forbidden: {text}", status_code=403)
        else:
            text = await response.text()
            raise IntegrationError(
                f"API error: {response.status} - {text}",
                status_code=response.status
            )
    
    async def get(self, endpoint: str, token: Optional[TokenInfo] = None, **kwargs):
        """GET request."""
        return await self._request("GET", endpoint, token, **kwargs)
    
    async def post(self, endpoint: str, token: Optional[TokenInfo] = None, **kwargs):
        """POST request."""
        return await self._request("POST", endpoint, token, **kwargs)
    
    async def patch(self, endpoint: str, token: Optional[TokenInfo] = None, **kwargs):
        """PATCH request."""
        return await self._request("PATCH", endpoint, token, **kwargs)
    
    async def delete(self, endpoint: str, token: Optional[TokenInfo] = None, **kwargs):
        """DELETE request."""
        return await self._request("DELETE", endpoint, token, **kwargs)
