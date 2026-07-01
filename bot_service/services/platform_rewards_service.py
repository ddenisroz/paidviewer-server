import logging
from typing import Dict, Any, List, Optional
from fastapi import HTTPException

from api.vk_api import vk_api
import asyncio

from services.user_service import UserService

# [REF] New Integrations
from integrations.twitch.client import TwitchClient
from integrations.twitch.oauth import TwitchOAuth
from integrations.base import TokenInfo, IntegrationError, TokenExpiredError, RateLimitError, AuthenticationError

logger = logging.getLogger('bot_service')

TWITCH_AFFILIATE_REQUIRED_MESSAGE = (
    "Twitch разрешает создавать награды только для каналов со статусом Affiliate или Partner."
)
VK_REWARD_MANAGE_SCOPES = {"channel:points:rewards"}
VK_REWARD_DEMANDS_SCOPES = {"channel:points:rewards:demands"}


_platform_rewards_service_singleton: "PlatformRewardsService | None" = None


def get_platform_rewards_service() -> "PlatformRewardsService":
    """Lazy singleton to avoid heavy/strict initialization during module import."""
    global _platform_rewards_service_singleton
    if _platform_rewards_service_singleton is None:
        _platform_rewards_service_singleton = PlatformRewardsService()
    return _platform_rewards_service_singleton


class PlatformRewardsService:
    """
    Service for managing rewards on external platforms (Twitch, VK).
    Delegates to platform-specific API clients.
    """
    def __init__(self):
        self.user_service = UserService()
        # Initialize Twitch Integration
        self.twitch_oauth = TwitchOAuth.from_settings()
        self.twitch_client = TwitchClient(self.twitch_oauth)

    def _get_token_info(self, token_model) -> TokenInfo:
        """Convert DB Token model to TokenInfo"""
        return TokenInfo(
            access_token=token_model.access_token,
            refresh_token=token_model.refresh_token,
            expires_at=token_model.expires_at.timestamp() if token_model.expires_at else None,
            scopes=token_model.scopes
        )

    @staticmethod
    def _normalize_scopes(raw_scopes) -> set[str]:
        if isinstance(raw_scopes, list):
            return {str(scope).strip() for scope in raw_scopes if str(scope).strip()}
        if isinstance(raw_scopes, str):
            normalized = raw_scopes.replace(",", " ")
            return {scope.strip() for scope in normalized.split(" ") if scope.strip()}
        return set()

    @staticmethod
    def _is_twitch_affiliate_requirement_error(message: str | None) -> bool:
        if not message:
            return False
        lowered = message.lower()
        return (
            "affiliate" in lowered
            or "partner" in lowered
            or "channel points" in lowered
            or "custom reward" in lowered
        )

    def _require_vk_scopes(self, token_model, required_scopes: set[str]):
        granted_scopes = self._normalize_scopes(getattr(token_model, "scopes", None))
        missing_scopes = sorted(required_scopes - granted_scopes)
        if missing_scopes:
            raise HTTPException(
                status_code=403,
                detail=(
                    "У токена VK Live не хватает прав: "
                    + ", ".join(missing_scopes)
                    + ". Переавторизуйте интеграцию VK Live."
                ),
            )

    def _get_vk_channel_name_or_raise(self, user_id: int, db) -> str:
        channel_name = self.user_service.get_vk_channel_name(user_id, db)
        if not channel_name:
            raise HTTPException(
                status_code=404,
                detail="Не найден VK Live канал. Подключите интеграцию VK Live заново.",
            )
        return channel_name

    async def get_rewards(self, user_id: int, platform: str, db) -> List[Dict[str, Any]]:
        """Get rewards from platform."""
        token = self.user_service.get_user_token(user_id, platform.lower(), db)
        if not token:
            raise HTTPException(status_code=404, detail=f"Token for platform {platform} not found")

        decrypted_token = self.user_service.decrypt_access_token(token.access_token) # Legacy decrypt? 
        # Wait, get_user_token returns model with likely encrypted token if stored encrypted.
        # But TokenInfo expects raw token. 
        # Ensure we pass the usable token. 
        # If UserService.decrypt_access_token handles it, use it.
        # The existing code used `decrypted_token` string.
        
        # NOTE: TokenInfo expects the RAW valid access token string to send in headers.
        
        if platform.lower() == 'twitch':
            token_info = self._get_token_info(token)
            # Override access_token with decrypted one if needed.
            token_info.access_token = decrypted_token 
            
            return await self._get_twitch_rewards(token.platform_user_id, token_info)
        elif platform.lower() == 'vk':
            self._require_vk_scopes(token, VK_REWARD_MANAGE_SCOPES)
            channel_name = self._get_vk_channel_name_or_raise(user_id, db)
            return await self._get_vk_rewards(channel_name, decrypted_token)
        else:
            raise HTTPException(status_code=400, detail="Unsupported platform")

    async def _get_twitch_rewards(self, broadcaster_id: str, token_info: TokenInfo) -> List[Dict[str, Any]]:
        if not broadcaster_id:
             raise HTTPException(status_code=404, detail="Twitch broadcaster ID not found")
        
        try:
            return await self.twitch_client.get_custom_rewards(broadcaster_id, token_info, only_manageable=True)
        except IntegrationError as e:
            self._handle_integration_error(e)

    async def _get_vk_rewards(self, channel_name: str, access_token: str) -> List[Dict[str, Any]]:
        rewards = await vk_api.get_rewards_manage_info(channel_name, access_token)
        if rewards is None:
            rewards = await vk_api.get_channel_rewards(channel_name, access_token)
        if rewards is None:
            raise HTTPException(
                status_code=400,
                detail="Failed to fetch VK rewards. Verify that channel points are enabled and the token has the required scopes."
            )
        
        # Normalize VK rewards
        normalized_rewards = []
        for reward in rewards:
            is_enabled = not reward.get('is_disabled', False)
            normalized_reward = {
                **reward,
                'cost': reward.get('price', 0),
                'is_enabled': is_enabled
            }
            normalized_rewards.append(normalized_reward)
        return normalized_rewards

    async def create_reward(self, user_id: int, platform: str, reward_data: Dict[str, Any], db) -> Dict[str, Any]:
        """Create a reward on the platform."""
        token = self.user_service.get_user_token(user_id, platform.lower(), db)
        if not token:
            raise HTTPException(status_code=404, detail=f"Token for platform {platform} not found")
        
        decrypted_token = self.user_service.decrypt_access_token(token.access_token)

        if platform.lower() == 'twitch':
            broadcaster_id = token.platform_user_id
            if not broadcaster_id:
                 raise HTTPException(status_code=404, detail="Twitch broadcaster ID not found")
            
            # Map data to Twitch format if needed (handled by caller or here?)
            # The API endpoint constructed specific dictionaries. 
            # Ideally the service receives a DTO or a dict and maps it.
            # For simplicity, assuming caller passes platform-specific dict or we map generic one.
            # Looking at existing code, API constructed `twitch_reward_data`.
            # Let's assume generic input and map it here, OR expect the caller to pass prepared data.
            # Since we want to remove logic from API, WE should map it here.
            # But the endpoints had different inputs (`CreateRewardRequest`).
            # I will accept the Pydantic model dict or similar.
            
            # Let's do the mapping if we receive generic keys.
            # If `reward_data` has 'title', 'cost' etc.
            
            twitch_data = self._map_to_twitch_create(reward_data)
            
            token_info = self._get_token_info(token)
            token_info.access_token = decrypted_token
            
            try:
                result = await self.twitch_client.create_custom_reward(broadcaster_id, token_info, twitch_data)
                return result
            except IntegrationError as e:
                self._handle_integration_error(e)
                
        elif platform.lower() == 'vk':
            self._require_vk_scopes(token, VK_REWARD_MANAGE_SCOPES)
            channel_name = self._get_vk_channel_name_or_raise(user_id, db)
            vk_data = self._map_to_vk_create(reward_data)
            
            result = await vk_api.create_channel_reward(channel_name, decrypted_token, vk_data)
            if not result:
                raise HTTPException(status_code=400, detail="VK Live API failed to create the reward")
            return result
        
        return None

    def _map_to_twitch_create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Map generic reward data to Twitch format."""
        twitch_data = {
            "title": data.get("title"),
            "prompt": data.get("description"), # Twitch uses prompt for description
            "cost": data.get("cost"),
            "is_enabled": data.get("is_enabled", True),
            "background_color": data.get("background_color", "#9147FF"),
            "is_user_input_required": data.get("is_user_input_required", False),
            "should_redemptions_skip_request_queue": data.get("should_redemptions_skip_request_queue", False)
        }
        
        # Max per stream
        if data.get("max_per_stream") and data["max_per_stream"] > 0:
            twitch_data["is_max_per_stream_enabled"] = True
            twitch_data["max_per_stream"] = data["max_per_stream"]
            
        # Max per user per stream
        if data.get("max_per_user_per_stream") and data["max_per_user_per_stream"] > 0:
            twitch_data["is_max_per_user_per_stream_enabled"] = True
            twitch_data["max_per_user_per_stream"] = data["max_per_user_per_stream"]
            
        # Global cooldown
        if data.get("global_cooldown_seconds") and data["global_cooldown_seconds"] > 0:
            twitch_data["is_global_cooldown_enabled"] = True
            twitch_data["global_cooldown_seconds"] = data["global_cooldown_seconds"]
            
        return twitch_data

    def _map_to_vk_create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Map generic reward data to VK format."""
        price = data.get("cost")
        try:
            price = int(price) if price is not None else None
        except (TypeError, ValueError):
            price = None
        vk_data = {
            "name": data.get("title"),
            "description": data.get("description"),
            "price": price,
            "is_message_required": data.get("is_message_required", data.get("is_user_input_required", False)),
        }
        
        # Only add optional fields if they have a non-zero value
        max_uses_count = data.get("max_uses_count", data.get("max_per_stream", 0) or 0)
        try:
            max_uses_count = int(max_uses_count) if max_uses_count is not None else 0
        except (TypeError, ValueError):
            max_uses_count = 0
        if max_uses_count and max_uses_count > 0:
            vk_data["max_uses_count"] = max_uses_count
            
        max_uses_count_per_user = data.get("max_uses_count_per_user", data.get("max_per_user_per_stream", 0) or 0)
        try:
            max_uses_count_per_user = int(max_uses_count_per_user) if max_uses_count_per_user is not None else 0
        except (TypeError, ValueError):
            max_uses_count_per_user = 0
        if max_uses_count_per_user and max_uses_count_per_user > 0:
            vk_data["max_uses_count_per_user"] = max_uses_count_per_user
            
        repair_timeout = data.get("repair_timeout", 0)
        try:
            repair_timeout = int(repair_timeout) if repair_timeout is not None else 0
        except (TypeError, ValueError):
            repair_timeout = 0
        if repair_timeout and repair_timeout > 0:
            vk_data["repair_timeout"] = repair_timeout
            
        return vk_data

    async def update_reward(self, user_id: int, platform: str, reward_id: str, reward_data: Dict[str, Any], db) -> Dict[str, Any]:
        token = self.user_service.get_user_token(user_id, platform.lower(), db)
        if not token:
            raise HTTPException(status_code=404, detail=f"Token for platform {platform} not found")

        decrypted_token = self.user_service.decrypt_access_token(token.access_token)

        if platform.lower() == 'twitch':
            broadcaster_id = token.platform_user_id
            twitch_data = self._map_to_twitch_create(reward_data) # Use same mapping
            
            token_info = self._get_token_info(token)
            token_info.access_token = decrypted_token
            
            try:
                result = await self.twitch_client.update_custom_reward(broadcaster_id, reward_id, token_info, twitch_data)
                return result
            except IntegrationError as e:
                self._handle_integration_error(e)

        elif platform.lower() == 'vk':
            self._require_vk_scopes(token, VK_REWARD_MANAGE_SCOPES)
            channel_name = self._get_vk_channel_name_or_raise(user_id, db)
            vk_data = self._map_to_vk_create(reward_data)
            
            result = await vk_api.edit_channel_reward(channel_name, reward_id, decrypted_token, vk_data)
            if not result:
                raise HTTPException(status_code=400, detail="VK Live API failed to update the reward")
            return result
            
    async def delete_reward(self, user_id: int, platform: str, reward_id: str, db) -> bool:
        token = self.user_service.get_user_token(user_id, platform.lower(), db)
        if not token:
             raise HTTPException(status_code=404, detail=f"Token for platform {platform} not found")

        decrypted_token = self.user_service.decrypt_access_token(token.access_token)
        
        if platform.lower() == 'twitch':
            broadcaster_id = token.platform_user_id
            token_info = self._get_token_info(token)
            token_info.access_token = decrypted_token
            
            try:
                result = await self.twitch_client.delete_custom_reward(broadcaster_id, reward_id, token_info)
                return result
            except IntegrationError as e:
                self._handle_integration_error(e)
                
        elif platform.lower() == 'vk':
            self._require_vk_scopes(token, VK_REWARD_MANAGE_SCOPES)
            channel_name = self._get_vk_channel_name_or_raise(user_id, db)
            # Add logic for clearing demands if needed? The original code had complex logic for VK delete.
            # I should incorporate that logic here or simplified.
            # The original code had "FIX: VK API não permite..." with loop to reject demands.
            # I will assume standard delete for now, or copy that logic.
            # To be safe, I'll copy the robust logic to a helper _delete_vk_reward_robust.
            return await self._delete_vk_reward_robust(channel_name, reward_id, decrypted_token)
            
    async def get_redemptions(self, user_id: int, platform: str, reward_id: str, status: Optional[str], db) -> List[Dict[str, Any]]:
        token = self.user_service.get_user_token(user_id, platform.lower(), db)
        if not token:
             raise HTTPException(status_code=404, detail=f"Token for platform {platform} not found")
        
        decrypted_token = self.user_service.decrypt_access_token(token.access_token)
        
        if platform.lower() == 'twitch':
            # Missing method in TwitchClient!
            # We found a gap. TwitchClient doesn't have get_custom_reward_redemptions.
            # We need to add it to TwitchClient or generic client.
            # For now, let's assume I will add it or it exists and I missed it?
            # I read imports... it wasn't there.
            # I must ADD it to TwitchClient.
            # But I am editing this service now.
            # I will assume it's there and then update TwitchClient.
            broadcaster_id = token.platform_user_id
            token_info = self._get_token_info(token)
            token_info.access_token = decrypted_token

            try:
                # Assuming I will add this method
                return await self.twitch_client.get_reward_redemptions(broadcaster_id, reward_id, token_info, status=status)
            except IntegrationError as e:
                self._handle_integration_error(e)
                
        elif platform.lower() == 'vk':
            self._require_vk_scopes(token, VK_REWARD_DEMANDS_SCOPES)
            channel_name = self._get_vk_channel_name_or_raise(user_id, db)
            # VK redemptions are demands
            result = await vk_api.get_reward_demands(channel_name, decrypted_token)
            if result and isinstance(result, dict):
                 return result.get("demands", []) or result.get("items", []) or []
            return []
            
        return []

    async def update_redemption_status(self, user_id: int, platform: str, reward_id: str, redemption_id: str, status: str, db) -> bool:
        token = self.user_service.get_user_token(user_id, platform.lower(), db)
        if not token:
             raise HTTPException(status_code=404, detail=f"Token for platform {platform} not found")
             
        decrypted_token = self.user_service.decrypt_access_token(token.access_token)
        
        if platform.lower() == 'twitch':
            broadcaster_id = token.platform_user_id
            token_info = self._get_token_info(token)
            token_info.access_token = decrypted_token
            
            try:
                # Check method in TwitchClient
                return await self.twitch_client.update_redemption_status(broadcaster_id, reward_id, redemption_id, token_info, status)
            except IntegrationError as e:
                self._handle_integration_error(e)
                
        elif platform.lower() == 'vk':
            self._require_vk_scopes(token, VK_REWARD_DEMANDS_SCOPES)
            channel_name = self._get_vk_channel_name_or_raise(user_id, db)
            demand_ids = [int(redemption_id)]
            if status.lower() == 'fulfilled':
                return await vk_api.accept_reward_demands(channel_name, decrypted_token, demand_ids)
            elif status.lower() == 'canceled':
                return await vk_api.reject_reward_demands(channel_name, decrypted_token, demand_ids)
                
        return False

    async def _delete_vk_reward_robust(self, channel_name, reward_id, access_token):
        """
        Robustly delete a VK reward handling active demands and enabled state.
        """
        # 1. Reject active demands
        try:
            demands_data = await vk_api.get_reward_demands(channel_name, access_token, limit=100)
            if demands_data:
                demands_list = demands_data.get("demands", []) or demands_data.get("items", []) or []
                if isinstance(demands_list, list):
                    reward_demands = [
                        d for d in demands_list 
                        if str(d.get("reward_id") or d.get("reward", {}).get("id", "")) == str(reward_id)
                    ]
                    
                    demand_ids = [
                        int(d.get("id") or d.get("demand_id")) 
                        for d in reward_demands 
                        if d.get("id") or d.get("demand_id")
                    ]
                    
                    if demand_ids:
                        await vk_api.reject_reward_demands(channel_name, access_token, demand_ids)
                        await asyncio.sleep(0.5)
        except Exception:
            logger.exception("Error handling demands during delete")
            await asyncio.sleep(0.3)

        # 2. Disable if enabled
        try:
             await vk_api.disable_channel_reward(channel_name, reward_id, access_token)
             await asyncio.sleep(0.5)
        except Exception:
             await asyncio.sleep(0.3)

        # 3. Delete
        return await vk_api.delete_channel_reward(channel_name, reward_id, access_token)

    async def toggle_reward(self, user_id: int, platform: str, reward_id: str, is_enabled: bool, db) -> bool:
        token = self.user_service.get_user_token(user_id, platform.lower(), db)
        if not token:
             raise HTTPException(status_code=404, detail=f"Token for platform {platform} not found")
        
        decrypted_token = self.user_service.decrypt_access_token(token.access_token)
        
        if platform.lower() == 'vk':
            self._require_vk_scopes(token, VK_REWARD_MANAGE_SCOPES)
            channel_name = self._get_vk_channel_name_or_raise(user_id, db)
            if is_enabled:
                return await vk_api.enable_channel_reward(channel_name, reward_id, decrypted_token)
            else:
                return await vk_api.disable_channel_reward(channel_name, reward_id, decrypted_token)
        elif platform.lower() == 'twitch':
            return await self.update_reward(user_id, platform, reward_id, {"is_enabled": is_enabled}, db)
            
        return False

    async def get_demands(self, user_id: int, platform: str, db) -> List[Dict[str, Any]]:
        if platform.lower() != 'vk':
             # Twitch doesn't have "demands" API exposed same way here, usually redemptions
             return []
             
        token = self.user_service.get_user_token(user_id, 'vk', db)
        if not token:
             raise HTTPException(status_code=404, detail="VK token not found")
        self._require_vk_scopes(token, VK_REWARD_DEMANDS_SCOPES)
        channel_name = self._get_vk_channel_name_or_raise(user_id, db)
        decrypted_token = self.user_service.decrypt_access_token(token.access_token)
        
        result = await vk_api.get_reward_demands(channel_name, decrypted_token)
        # Handle dict response
        if result and isinstance(result, dict):
             return result.get("demands", []) or result.get("items", []) or []
        return []

    async def process_demands(self, user_id: int, platform: str, demand_ids: List[int], action: str, db) -> bool:
        if platform.lower() != 'vk':
            raise HTTPException(status_code=400, detail="Only VK supports demand processing")
            
        token = self.user_service.get_user_token(user_id, 'vk', db)
        if not token:
             raise HTTPException(status_code=404, detail="VK token not found")
        self._require_vk_scopes(token, VK_REWARD_DEMANDS_SCOPES)
        channel_name = self._get_vk_channel_name_or_raise(user_id, db)
        decrypted_token = self.user_service.decrypt_access_token(token.access_token)
        
        if action == 'accept':
            return await vk_api.accept_reward_demands(channel_name, decrypted_token, demand_ids)
        elif action == 'reject':
            return await vk_api.reject_reward_demands(channel_name, decrypted_token, demand_ids)
        else:
            raise HTTPException(status_code=400, detail="Invalid action")

    def _handle_integration_error(self, e: IntegrationError):
        """Map IntegrationError to HTTPException"""
        error_message = getattr(e, "message", None) or str(e) or "Platform API request failed"
        if self._is_twitch_affiliate_requirement_error(error_message):
            raise HTTPException(status_code=403, detail=TWITCH_AFFILIATE_REQUIRED_MESSAGE)
        if isinstance(e, TokenExpiredError):
            raise HTTPException(status_code=401, detail="Token expired")
        elif isinstance(e, RateLimitError):
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        elif isinstance(e, AuthenticationError):
            raise HTTPException(status_code=403, detail=error_message)
        else:
            # Check status code in Base Exception
            if e.status_code:
                raise HTTPException(status_code=e.status_code, detail=error_message)
            raise HTTPException(status_code=500, detail="Platform API request failed")


