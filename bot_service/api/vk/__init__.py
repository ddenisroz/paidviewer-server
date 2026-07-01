# api/vk/__init__.py
"""
VK Live API Client Package - Split into focused modules.

This package provides a clean interface to VK Live API with:
- VKBase: Shared base functionality, rate limiting
- VKAuth: Token management, OAuth
- VKStream: Stream/channel info, updates
- VKRewards: Channel Points, rewards
"""
from .vk_base import VKBase, RateLimiter
from .vk_auth import VKAuth
from .vk_stream import VKStream
from .vk_rewards import VKRewards

__all__ = [
    'VKBase',
    'RateLimiter',
    'VKAuth',
    'VKStream',
    'VKRewards',
]
