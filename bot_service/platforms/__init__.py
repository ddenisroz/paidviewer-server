"""
Platform abstraction layer for streaming platforms
"""
from .base import StreamingPlatform, PlatformConfig
from .registry import platform_registry

__all__ = ['StreamingPlatform', 'PlatformConfig', 'platform_registry']
