"""Platform constants for TTS bot service.

This module defines platform-related constants to avoid hardcoded values.
"""

# TTS platform toggles start disabled until the integration is authorized.
DEFAULT_ENABLED_PLATFORMS = []

# All supported platforms
SUPPORTED_PLATFORMS = ["twitch", "vk", "youtube"]

# Platform display names
PLATFORM_NAMES = {
    "twitch": "Twitch",
    "vk": "VK Live",
    "youtube": "YouTube"
}
