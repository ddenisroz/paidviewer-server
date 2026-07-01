"""
VK API Base Module
Contains shared logic, rate limiting, and base client structure.
"""
import ssl
import time
import asyncio
import logging
import os
import urllib3
import aiohttp
from dataclasses import dataclass

_VK_INSECURE_SSL = os.getenv("VK_INSECURE_SSL", "false").strip().lower() in {"1", "true", "yes", "on"}
if _VK_INSECURE_SSL:
    # Only suppress warnings in explicitly insecure dev mode.
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

# Global timeout configuration
VK_API_TIMEOUT = aiohttp.ClientTimeout(total=30, connect=10)

@dataclass
class RateLimiter:
    """Rate limiter for VK API requests."""
    last_request_time: float = 0
    max_requests_per_second: int = 3

    async def wait(self) -> None:
        """Wait if necessary to comply with rate limits."""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        if time_since_last_request < 1.0 / self.max_requests_per_second:
            wait_time = (1.0 / self.max_requests_per_second) - time_since_last_request
            await asyncio.sleep(wait_time)
        self.last_request_time = time.time()


class VKBase:
    """Base class for VK API modules."""
    
    BASE_URL = "https://api.live.vkvideo.ru"


    
    def __init__(self) -> None:
        self.rate_limiter = RateLimiter()
        
        # SSL context configuration; secure by default.
        self.ssl_context = ssl.create_default_context()
        if _VK_INSECURE_SSL:
            logger.warning("VK API SSL verification is disabled via VK_INSECURE_SSL=true")
            self.ssl_context.check_hostname = False
            self.ssl_context.verify_mode = ssl.CERT_NONE


