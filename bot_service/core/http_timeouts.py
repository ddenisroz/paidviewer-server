# bot_service/core/http_timeouts.py
"""HTTP timeout constants for external API requests."""
import aiohttp

# OAuth endpoints
OAUTH_REQUEST_TIMEOUT = 30.0  # seconds
"""Timeout for OAuth requests (token exchange, user info)."""

OAUTH_REQUEST_TIMEOUT_OBJ = aiohttp.ClientTimeout(total=30, connect=10)
"""aiohttp timeout object for OAuth requests."""

# Token validation
TOKEN_VALIDATION_TIMEOUT = 10.0  # seconds
"""Timeout for token validation against platform APIs."""

TOKEN_VALIDATION_TIMEOUT_OBJ = aiohttp.ClientTimeout(total=10, connect=5)
"""aiohttp timeout object for token validation."""

# VK Live API (also defined as aiohttp.ClientTimeout in vk_api.py)
VK_API_TIMEOUT = 15.0  # seconds
"""Timeout for VK Live API requests (legacy scalar form)."""

# Twitch API timeout is intentionally shorter to reduce long stalls on network errors.
TWITCH_API_TIMEOUT = aiohttp.ClientTimeout(total=10, connect=5)
"""Timeout for Twitch API requests (10 seconds max, reduced from 30)."""

# DonationAlerts API
DONATIONALERTS_API_TIMEOUT = 15.0  # seconds
"""Timeout for DonationAlerts API requests."""

DONATIONALERTS_API_TIMEOUT_OBJ = aiohttp.ClientTimeout(total=15, connect=10)
"""aiohttp timeout object for DonationAlerts API."""

# General API
DEFAULT_API_TIMEOUT = aiohttp.ClientTimeout(total=30, connect=10)
"""Default timeout object for generic API requests."""

