# bot_service/integrations/__init__.py
"""
Integrations layer - isolated interfaces for external services.

This layer encapsulates all external API interaction logic:
- Twitch API, OAuth, EventSub
- VK Live API
- DonationAlerts API
- TTS Engines (Google, F5)

Key principles:
1. External-service failures must NOT crash the application
2. Retry logic and timeouts are configured centrally
3. Tokens are refreshed automatically
4. Each integration is fully isolated
"""

from .twitch import TwitchClient
from .vk import VKClient
from .donationalerts import DonationAlertsClient

__all__ = [
    "TwitchClient",
    "VKClient",
    "DonationAlertsClient",
]
