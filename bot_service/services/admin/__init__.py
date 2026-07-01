# bot_service/services/admin/__init__.py
"""
Administrative services package.

The former AdminAPI surface is split into focused services:
- whitelist_service: channel whitelist management
- blocked_bots_service: blocked bot management
- user_management_service: user administration
- bot_control_service: bot status and restart controls
- logs_service: log access helpers
- stats_service: dashboard statistics
"""

from .whitelist_service import WhitelistService
from .blocked_bots_service import BlockedBotsService
from .user_management_service import UserManagementService
from .bot_control_service import BotControlService
from .logs_service import LogsService
from .stats_service import AdminStatsService, get_admin_stats_service

# Singleton instances
whitelist_service = WhitelistService()
blocked_bots_service = BlockedBotsService()
user_management_service = UserManagementService()
bot_control_service = BotControlService()
logs_service = LogsService()

__all__ = [
    "WhitelistService",
    "BlockedBotsService",
    "UserManagementService",
    "BotControlService",
    "LogsService",
    "AdminStatsService",
    "get_admin_stats_service",
    "whitelist_service",
    "blocked_bots_service",
    "user_management_service",
    "bot_control_service",
    "logs_service",
]
