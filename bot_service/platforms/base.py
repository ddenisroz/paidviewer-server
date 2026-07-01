"""
Base interface for streaming platforms
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field


@dataclass
class PlatformCapabilities:
    """Normalized feature availability for a streaming platform."""

    roles: bool = True
    badges: bool = False
    reply_context: bool = False
    mention_context: bool = False
    moderation_actions: bool = False
    rewards: bool = False
    bot_status: bool = False
    supported_roles: list[str] = field(default_factory=list)
    moderation_actions_available: list[str] = field(default_factory=list)


@dataclass
class PlatformConfig:
    """Configuration for a streaming platform"""
    name: str  # 'twitch', 'vk', 'kick', 'youtube'
    display_name: str
    supports_oauth: bool
    supports_chat: bool
    supports_tts: bool
    supports_points: bool
    supports_categories: bool
    color: str  # Brand color for UI
    capabilities: PlatformCapabilities = field(default_factory=PlatformCapabilities)


class StreamingPlatform(ABC):
    """Abstract base class for streaming platforms"""

    def __init__(self, config: PlatformConfig):
        self.config = config

    @abstractmethod
    async def authenticate(self, code: str) -> Dict[str, Any]:
        """
        Handle OAuth authentication
        
        Args:
            code: OAuth authorization code
            
        Returns:
            Dict containing access_token, refresh_token, expires_in, etc.
        """
        pass

    @abstractmethod
    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """
        Get user information
        
        Args:
            access_token: User's access token
            
        Returns:
            Dict containing user_id, username, avatar_url, etc.
        """
        pass

    @abstractmethod
    async def update_stream_title(self, user_id: int, title: str) -> bool:
        """
        Update stream title
        
        Args:
            user_id: Unified user ID from database
            title: New stream title
            
        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def update_stream_category(self, user_id: int, category_id: str) -> bool:
        """
        Update stream category
        
        Args:
            user_id: Unified user ID from database
            category_id: Platform-specific category ID
            
        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def search_categories(self, query: str) -> List[Dict[str, Any]]:
        """
        Search for categories
        
        Args:
            query: Search query
            
        Returns:
            List of category dicts with id, name, box_art_url, etc.
        """
        pass

    @abstractmethod
    async def get_stream_status(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Get current stream status
        
        Args:
            username: Platform username
            
        Returns:
            Dict with stream info if online, None if offline
        """
        pass

    @abstractmethod
    async def get_channel_info(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Get channel information (works for offline streams)
        
        Args:
            username: Platform username
            
        Returns:
            Dict with channel info (title, category, etc.)
        """
        pass

    @abstractmethod
    async def send_chat_message(self, user_id: int, message: str) -> bool:
        """
        Send message to chat
        
        Args:
            user_id: Unified user ID from database
            message: Message to send
            
        Returns:
            True if successful, False otherwise
        """
        pass

    # Optional methods (not all platforms support all features)

    async def create_reward(self, user_id: int, reward_data: Dict) -> Optional[str]:
        """
        Create channel points reward (if supported)
        
        Args:
            user_id: Unified user ID from database
            reward_data: Reward configuration
            
        Returns:
            Reward ID if successful, None otherwise
        """
        return None

    async def update_reward(self, user_id: int, reward_id: str, reward_data: Dict) -> bool:
        """
        Update channel points reward (if supported)
        
        Args:
            user_id: Unified user ID from database
            reward_id: Platform-specific reward ID
            reward_data: Updated reward configuration
            
        Returns:
            True if successful, False otherwise
        """
        return False

    async def delete_reward(self, user_id: int, reward_id: str) -> bool:
        """
        Delete channel points reward (if supported)
        
        Args:
            user_id: Unified user ID from database
            reward_id: Platform-specific reward ID
            
        Returns:
            True if successful, False otherwise
        """
        return False

    async def get_user_roles(self, username: str, channel_name: str) -> List[str]:
        """
        Get user roles on a channel (broadcaster, moderator, vip, subscriber, etc.)
        
        Args:
            username: User's platform username
            channel_name: Channel name
            
        Returns:
            List of role strings
        """
        return []
