# bot_service/integrations/twitch/__init__.py
"""
Twitch Integration Layer.

Isolated module for Twitch API access:
- OAuth 2.0 (app token, user token, refresh)
- Helix API (users, streams, channels)
- Channel Points (custom rewards)
- Moderation
"""

from .client import TwitchClient
from .oauth import TwitchOAuth

__all__ = ["TwitchClient", "TwitchOAuth"]
