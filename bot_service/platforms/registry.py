"""
Platform registry for managing all streaming platforms
"""
from typing import Dict, Optional, List
import logging
from .base import StreamingPlatform

logger = logging.getLogger(__name__)


class PlatformRegistry:
    """Central registry for all streaming platforms"""

    def __init__(self):
        self._platforms: Dict[str, StreamingPlatform] = {}
        self._initialized = False

    def _register_platforms(self):
        """Register all available platforms"""
        if self._initialized:
            return

        try:
            # Import and register Twitch
            from .twitch import TwitchPlatform
            self.register(TwitchPlatform())
            logger.info("Registered Twitch platform")
        except Exception as e:
            logger.error(f"Failed to register Twitch platform: {e}")

        try:
            # Import and register VK
            from .vk import VKPlatform
            self.register(VKPlatform())
            logger.info("Registered VK platform")
        except Exception as e:
            logger.error(f"Failed to register VK platform: {e}")

        self._initialized = True
        logger.info(f"Platform registry initialized with {len(self._platforms)} platforms")

    def register(self, platform: StreamingPlatform):
        """
        Register a new platform
        
        Args:
            platform: StreamingPlatform instance to register
        """
        self._platforms[platform.config.name] = platform
        logger.debug(f"Registered platform: {platform.config.display_name}")

    def get(self, name: str) -> Optional[StreamingPlatform]:
        """
        Get platform by name
        
        Args:
            name: Platform name (e.g., 'twitch', 'vk')
            
        Returns:
            StreamingPlatform instance or None if not found
        """
        # Lazy initialization
        if not self._initialized:
            self._register_platforms()

        return self._platforms.get(name)

    def get_all(self) -> Dict[str, StreamingPlatform]:
        """
        Get all registered platforms
        
        Returns:
            Dict mapping platform names to StreamingPlatform instances
        """
        # Lazy initialization
        if not self._initialized:
            self._register_platforms()

        return self._platforms.copy()

    def get_configs(self) -> List[Dict]:
        """
        Get all platform configurations for frontend
        
        Returns:
            List of platform configuration dicts
        """
        # Lazy initialization
        if not self._initialized:
            self._register_platforms()

        configs = []
        for platform in self._platforms.values():
            config = platform.config
            capabilities = config.capabilities
            configs.append({
                'name': config.name,
                'displayName': config.display_name,
                'supportsOAuth': config.supports_oauth,
                'supportsChat': config.supports_chat,
                'supportsTts': config.supports_tts,
                'supportsPoints': config.supports_points,
                'supportsCategories': config.supports_categories,
                'color': config.color,
                'capabilities': {
                    'roles': capabilities.roles,
                    'badges': capabilities.badges,
                    'reply_context': capabilities.reply_context,
                    'mention_context': capabilities.mention_context,
                    'moderation_actions': capabilities.moderation_actions,
                    'rewards': capabilities.rewards,
                    'bot_status': capabilities.bot_status,
                    'supported_roles': list(capabilities.supported_roles),
                    'moderation_actions_available': list(capabilities.moderation_actions_available),
                },
            })
        return configs

    def is_valid_platform(self, name: str) -> bool:
        """
        Check if a platform name is valid
        
        Args:
            name: Platform name to check
            
        Returns:
            True if platform exists, False otherwise
        """
        # Lazy initialization
        if not self._initialized:
            self._register_platforms()

        return name in self._platforms


# Global registry instance
platform_registry = PlatformRegistry()
