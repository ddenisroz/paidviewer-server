"""Helpers for fetching Twitch chat badges."""
import aiohttp
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# In-memory badge cache to avoid repeated upstream requests.
GLOBAL_BADGES_CACHE: Optional[Dict] = None
CHANNEL_BADGES_CACHE: Dict[str, Dict] = {}  # {channel_id: badges_dict}


async def get_global_badges(client_id: str, access_token: str) -> Dict:
    """Fetch global Twitch badges."""
    global GLOBAL_BADGES_CACHE

    if GLOBAL_BADGES_CACHE:
        return GLOBAL_BADGES_CACHE

    url = "https://api.twitch.tv/helix/chat/badges/global"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Client-Id": client_id
    }

    try:
        # Timeout: 10 seconds to connect, 30 seconds to read.
        timeout = aiohttp.ClientTimeout(total=30, connect=10)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()

                    # Normalize to {badge_id: {version: url}}.
                    badges_dict = {}
                    for badge_set in data.get('data', []):
                        set_id = badge_set['set_id']
                        badges_dict[set_id] = {}
                        for version in badge_set['versions']:
                            badges_dict[set_id][version['id']] = {
                                'image_url_1x': version['image_url_1x'],
                                'image_url_2x': version['image_url_2x'],
                                'image_url_4x': version['image_url_4x'],
                            }

                    GLOBAL_BADGES_CACHE = badges_dict
                    logger.info(f"[OK] Loaded {len(badges_dict)} global badge sets")
                    return badges_dict
                else:
                    logger.error(f"[ERROR] Failed to fetch global badges: {response.status}")
                    return {}
    except Exception:
        logger.exception("[ERROR] Error fetching global badges")
        return {}


async def get_channel_badges(broadcaster_id: str, client_id: str, access_token: str) -> Dict:
    """Fetch channel-specific Twitch badges."""
    if broadcaster_id in CHANNEL_BADGES_CACHE:
        return CHANNEL_BADGES_CACHE[broadcaster_id]

    url = f"https://api.twitch.tv/helix/chat/badges?broadcaster_id={broadcaster_id}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Client-Id": client_id
    }

    try:
        # Timeout: 10 seconds to connect, 30 seconds to read.
        timeout = aiohttp.ClientTimeout(total=30, connect=10)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()

                    # Normalize to the internal lookup format.
                    badges_dict = {}
                    for badge_set in data.get('data', []):
                        set_id = badge_set['set_id']
                        badges_dict[set_id] = {}
                        for version in badge_set['versions']:
                            badges_dict[set_id][version['id']] = {
                                'image_url_1x': version['image_url_1x'],
                                'image_url_2x': version['image_url_2x'],
                                'image_url_4x': version['image_url_4x'],
                            }

                    CHANNEL_BADGES_CACHE[broadcaster_id] = badges_dict
                    logger.info(f"[OK] Loaded {len(badges_dict)} badge sets for channel {broadcaster_id}")
                    return badges_dict
                elif response.status == 400:
                    # 400 usually means the channel was not found or broadcaster_id is invalid.
                    error_text = await response.text()
                    logger.warning(f"[WARN] Channel badges not available for broadcaster {broadcaster_id}: {response.status} - {error_text}")
                    # Cache the empty result to avoid repeated failing requests.
                    CHANNEL_BADGES_CACHE[broadcaster_id] = {}
                    return {}
                elif response.status == 404:
                    # 404 means the channel was not found.
                    logger.warning(f"[WARN] Channel {broadcaster_id} not found")
                    CHANNEL_BADGES_CACHE[broadcaster_id] = {}
                    return {}
                else:
                    error_text = await response.text()
                    logger.error(f"[ERROR] Failed to fetch channel badges: {response.status} - {error_text}")
                    # Do not cache generic errors so retries can recover.
                    return {}
    except Exception:
        logger.exception("[ERROR] Error fetching channel badges")
        return {}


def get_badge_url(badge_id: str, version: str, global_badges: Dict, channel_badges: Dict, size: str = '2x') -> Optional[str]:
    """Resolve a badge image URL by badge id, version, and size."""
    # Prefer channel badges over global ones.
    if badge_id in channel_badges and version in channel_badges[badge_id]:
        return channel_badges[badge_id][version].get(f'image_url_{size}')

    # Fallback to global badges.
    if badge_id in global_badges and version in global_badges[badge_id]:
        return global_badges[badge_id][version].get(f'image_url_{size}')

    return None


