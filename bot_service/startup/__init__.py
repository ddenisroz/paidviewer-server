"""Application startup module exports."""

from .bot_initializer import initialize_all_bots, initialize_twitch_bot, initialize_vk_bot
from .bot_registry import BotRegistry, get_bot_registry
from .lifespan import lifespan

__all__ = [
    "BotRegistry",
    "get_bot_registry",
    "initialize_twitch_bot",
    "initialize_vk_bot",
    "initialize_all_bots",
    "lifespan",
]
