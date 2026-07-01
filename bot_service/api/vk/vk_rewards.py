"""
VK API Rewards Module
Handles channel points and custom rewards management.
"""
import logging
from typing import Optional, Dict, Any, List, Union, cast

import aiohttp

from .vk_auth import VKAuth
from .vk_base import VK_API_TIMEOUT
from utils.vk_channel_url import get_vk_channel_candidates, normalize_vk_channel_url

logger = logging.getLogger(__name__)

class VKRewards(VKAuth):
    """
    Channel points and rewards management for VK Live API.
    Refereces VKAuth for token handling (although most methods take access_token directly).
    """

    async def get_channel_points_balance(self, channel_url: str, access_token: str) -> Optional[Dict[str, Any]]:
        """Get channel points balance."""
        try:
            channel_url = normalize_vk_channel_url(channel_url)
            url = f"{self.BASE_URL}/v1/channel_point"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            params = {"channel_url": channel_url}

            # Use aiohttp with shared ssl_context instead of httpx
            async with aiohttp.ClientSession(timeout=VK_API_TIMEOUT) as session:
                async with session.get(url, headers=headers, params=params, ssl=self.ssl_context) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"Got VK channel points balance for {channel_url}")
                        return cast(Optional[Dict[str, Any]], data.get("data"))
                    else:
                        response_text = await response.text()
                        logger.error(f"VK channel points balance error: {response.status} - {response_text}")
                        return None

        except Exception:
            logger.exception("Error getting VK channel points balance")
            return None

    async def get_channel_rewards(self, channel_url: str, access_token: str) -> Optional[List[Dict[str, Any]]]:
        """Get list of channel rewards."""
        try:
            url = f"{self.BASE_URL}/v1/channel_point/rewards"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            async with aiohttp.ClientSession(timeout=VK_API_TIMEOUT) as session:
                for candidate in get_vk_channel_candidates(channel_url):
                    params = {"channel_url": candidate}
                    async with session.get(url, headers=headers, params=params, ssl=self.ssl_context) as response:
                        if response.status == 200:
                            data = await response.json()
                            return cast(Optional[List[Dict[str, Any]]], data.get("data", {}).get("rewards", []))
                        response_text = await response.text()
                        logger.error(f"VK channel rewards error ({candidate}): {response.status} - {response_text}")

        except Exception:
            logger.exception("Error getting VK channel rewards")
            return None

    async def create_channel_reward(self, channel_url: str, access_token: str, reward_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a new channel reward."""
        try:
            channel_url = normalize_vk_channel_url(channel_url)
            url = f"{self.BASE_URL}/v1/channel_point/reward/create"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            params = {"channel_url": channel_url}
            body = {"reward": reward_data}

            async with aiohttp.ClientSession(timeout=VK_API_TIMEOUT) as session:
                async with session.post(url, headers=headers, params=params, json=body, ssl=self.ssl_context) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"[OK] VK API Response for create reward: {data}")
                        logger.info(f"Created VK channel reward: {reward_data.get('name')}")
                        return cast(Optional[Dict[str, Any]], data.get("data"))
                    else:
                        response_text = await response.text()
                        logger.error(f"VK create reward error: {response.status} - {response_text}")
                        return None

        except Exception:
            logger.exception("Error creating VK channel reward")
            return None
    
    async def get_rewards_manage_info(self, channel_url: str, access_token: str) -> Optional[List[Dict[str, Any]]]:
        """Get rewards management info (for streamer)."""
        try:
            url = f"{self.BASE_URL}/v1/channel_point/rewards/manage_info"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            async with aiohttp.ClientSession(timeout=VK_API_TIMEOUT) as session:
                for candidate in get_vk_channel_candidates(channel_url):
                    params = {"channel_url": candidate}
                    async with session.get(url, headers=headers, params=params, ssl=self.ssl_context) as response:
                        if response.status == 200:
                            data = await response.json()
                            return cast(Optional[List[Dict[str, Any]]], data.get("data", {}).get("rewards", []))
                        response_text = await response.text()
                        logger.error(f"VK rewards manage info error ({candidate}): {response.status} - {response_text}")
        except Exception:
             logger.exception("Error getting VK rewards manage info")
             return None

    async def get_reward_demands(self, channel_url: str, access_token: str, limit: int = 20, offset: int = 0) -> Optional[Dict[str, Any]]:
        """Get reward demands list."""
        try:
            channel_url = normalize_vk_channel_url(channel_url)
            url = f"{self.BASE_URL}/v1/channel_point/reward/demands"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            params: Dict[str, Union[str, int]] = {
                "channel_url": str(channel_url),
                "limit": int(limit),
                "offset": int(offset)
            }

            async with aiohttp.ClientSession(timeout=VK_API_TIMEOUT) as session:
                async with session.get(url, headers=headers, params=params, ssl=self.ssl_context) as response:
                    if response.status == 200:
                        data = await response.json()
                        return cast(Optional[Dict[str, Any]], data.get("data"))
                    else:
                        response_text = await response.text()
                        logger.error(f"VK reward demands error: {response.status} - {response_text}")
                        return None
        except Exception:
            logger.exception("Error getting VK reward demands")
            return None

    async def accept_reward_demands(self, channel_url: str, access_token: str, demand_ids: List[int]) -> bool:
        """Accept reward demands."""
        try:
            channel_url = normalize_vk_channel_url(channel_url)
            url = f"{self.BASE_URL}/v1/channel_point/reward/demand/accept"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            params = {"channel_url": channel_url}
            body = {"demands": [{"id": demand_id} for demand_id in demand_ids]}

            async with aiohttp.ClientSession(timeout=VK_API_TIMEOUT) as session:
                async with session.post(url, headers=headers, params=params, json=body, ssl=self.ssl_context) as response:
                    if response.status == 200:
                        logger.info(f"Accepted VK reward demands: {demand_ids}")
                        return True
                    else:
                        response_text = await response.text()
                        logger.error(f"VK accept demands error: {response.status} - {response_text}")
                        return False
        except Exception:
            logger.exception("Error accepting VK reward demands")
            return False

    async def reject_reward_demands(self, channel_url: str, access_token: str, demand_ids: List[int]) -> bool:
        """Reject reward demands."""
        try:
            channel_url = normalize_vk_channel_url(channel_url)
            url = f"{self.BASE_URL}/v1/channel_point/reward/demand/reject"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            params = {"channel_url": channel_url}
            body = {"demands": [{"id": demand_id} for demand_id in demand_ids]}

            async with aiohttp.ClientSession(timeout=VK_API_TIMEOUT) as session:
                async with session.post(url, headers=headers, params=params, json=body, ssl=self.ssl_context) as response:
                    if response.status == 200:
                        logger.info(f"Rejected VK reward demands: {demand_ids}")
                        return True
                    else:
                        response_text = await response.text()
                        logger.error(f"VK reject demands error: {response.status} - {response_text}")
                        return False
        except Exception:
            logger.exception("Error rejecting VK reward demands")
            return False

    async def delete_channel_reward(self, channel_url: str, reward_id: str, access_token: str) -> bool:
        """Delete channel reward."""
        try:
            channel_url = normalize_vk_channel_url(channel_url)
            url = f"{self.BASE_URL}/v1/channel_point/reward/delete"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            params = {
                "channel_url": channel_url,
                "reward_id": reward_id
            }

            async with aiohttp.ClientSession(timeout=VK_API_TIMEOUT) as session:
                async with session.post(url, headers=headers, params=params, ssl=self.ssl_context) as response:
                    if response.status == 200:
                        logger.info(f"Deleted VK channel reward: {reward_id}")
                        return True
                    else:
                        response_text = await response.text()
                        logger.error(f"VK delete reward error: {response.status} - {response_text}")
                        return False
        except Exception:
            logger.exception("Error deleting VK channel reward")
            return False

    async def update_channel_reward(self, channel_url: str, reward_id: str, access_token: str, reward_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update channel reward."""
        try:
            channel_url = normalize_vk_channel_url(channel_url)
            url = f"{self.BASE_URL}/v1/channel_point/reward/edit"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            params = {
                "channel_url": channel_url,
                "reward_id": reward_id
            }
            body = {"reward": reward_data}

            async with aiohttp.ClientSession(timeout=VK_API_TIMEOUT) as session:
                async with session.post(url, headers=headers, params=params, json=body, ssl=self.ssl_context) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"Updated VK channel reward: {reward_id}")
                        return cast(Optional[Dict[str, Any]], data.get("data"))
                    else:
                        response_text = await response.text()
                        logger.error(f"VK update reward error: {response.status} - {response_text}")
                        return None
        except Exception:
            logger.exception("Error updating VK channel reward")
            return None

    async def enable_channel_reward(self, channel_url: str, reward_id: str, access_token: str) -> bool:
        """Enable channel reward."""
        try:
            channel_url = normalize_vk_channel_url(channel_url)
            url = f"{self.BASE_URL}/v1/channel_point/reward/enable"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            params = {
                "channel_url": channel_url,
                "reward_id": reward_id
            }

            async with aiohttp.ClientSession(timeout=VK_API_TIMEOUT) as session:
                async with session.post(url, headers=headers, params=params, ssl=self.ssl_context) as response:
                    if response.status == 200:
                        logger.info(f"Enabled VK channel reward: {reward_id}")
                        return True
                    else:
                        response_text = await response.text()
                        logger.error(f"VK enable reward error: {response.status} - {response_text}")
                        return False
        except Exception:
            logger.exception("Error enabling VK channel reward")
            return False

    async def disable_channel_reward(self, channel_url: str, reward_id: str, access_token: str) -> bool:
        """Disable channel reward."""
        try:
            channel_url = normalize_vk_channel_url(channel_url)
            url = f"{self.BASE_URL}/v1/channel_point/reward/disable"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            params = {
                "channel_url": channel_url,
                "reward_id": reward_id
            }

            async with aiohttp.ClientSession(timeout=VK_API_TIMEOUT) as session:
                async with session.post(url, headers=headers, params=params, ssl=self.ssl_context) as response:
                    if response.status == 200:
                        logger.info(f"Disabled VK channel reward: {reward_id}")
                        return True
                    else:
                        logger.error(f"VK disable reward error: {response.status} - {await response.text()}")
                        return False
        except Exception:
            logger.exception("Error disabling VK channel reward")
            return False

