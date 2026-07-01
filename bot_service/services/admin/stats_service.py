"""Statistics service for the admin panel."""
import logging
import shutil
import os
from datetime import timedelta
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from core.datetime_utils import utcnow_naive
from repositories.admin_stats_repository import AdminStatsRepository
logger = logging.getLogger(__name__)

class AdminStatsService:
    """Statistics service for the admin panel."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = AdminStatsRepository(db)

    def get_user_counts(self) -> Dict[str, int]:
        """Get user counts: total, active_today, active_week, new_this_month."""
        now = utcnow_naive()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_ago = now - timedelta(days=7)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return {'total': self.repo.count_users(), 'active_today': self.repo.count_active_users_since(today_start), 'active_week': self.repo.count_active_users_since(week_ago), 'new_this_month': self.repo.count_new_users_since(month_start), 'active': self.repo.count_users_by_status(is_active=True), 'blocked': self.repo.count_users_by_status(is_blocked=True)}

    def get_message_counts(self) -> Dict[str, int]:
        """Get message counts for various time periods."""
        now = utcnow_naive()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_ago = now - timedelta(days=7)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        day_ago = now - timedelta(days=1)
        hour_ago = now - timedelta(hours=1)
        return {'total': self.repo.count_messages(), 'today': self.repo.count_messages(today_start), 'week': self.repo.count_messages(week_ago), 'month': self.repo.count_messages(month_start), 'last_24h': self.repo.count_messages(day_ago), 'last_1h': self.repo.count_messages(hour_ago)}

    def get_session_counts(self) -> Dict[str, int]:
        """Get session statistics."""
        return {'active': self.repo.count_active_sessions()}

    def get_integration_counts(self) -> Dict[str, int]:
        """Get integration token statistics."""
        twitch = self.repo.count_active_tokens('twitch')
        vk = self.repo.count_active_tokens('vk')
        return {'twitch': twitch, 'vk': vk, 'total': twitch + vk}

    def get_error_counts(self) -> Dict[str, int]:
        """Get error statistics from SecurityLog."""
        day_ago = utcnow_naive() - timedelta(days=1)
        errors_24h = self.repo.count_errors_since(day_ago)
        return {'errors_24h': errors_24h}

    def get_tts_stats(self) -> Dict[str, int]:
        """Get TTS-related statistics."""
        return {'enabled_users': self.repo.count_tts_enabled_users()}

    def get_top_commands(self, limit: int=5) -> list:
        """Get top used commands."""
        top_cmds = self.repo.get_top_commands(limit)
        return [{'command': f'!{cmd[0]}', 'count': cmd[1] or 0} for cmd in top_cmds]

    def get_active_channels(self) -> list:
        """Get active channels data."""
        channels = self.repo.get_active_channels_settings()
        return [{'id': ch.id, 'channel_name': getattr(ch, 'channel_name', None), 'vk_channel_name': getattr(ch, 'vk_channel_name', None), 'platform': 'twitch' if getattr(ch, 'channel_name', None) else 'vk', 'tts_enabled': getattr(ch, 'tts_enabled', False), 'created_at': ch.created_at.isoformat() if ch.created_at else None} for ch in channels]

    @staticmethod
    def get_storage_stats() -> Dict[str, float]:
        """Get storage usage statistics."""
        storage_used_gb = 0.0
        storage_total_gb = 100.0
        try:
            logs_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'logs')
            if os.path.exists(logs_path):
                total_size = 0
                for (dirpath, dirnames, filenames) in os.walk(logs_path):
                    for filename in filenames:
                        filepath = os.path.join(dirpath, filename)
                        if os.path.exists(filepath):
                            total_size += os.path.getsize(filepath)
                storage_used_gb = round(total_size / 1024 ** 3, 2)
            disk_usage = shutil.disk_usage(logs_path if os.path.exists(logs_path) else os.getcwd())
            storage_total_gb = round(disk_usage.total / 1024 ** 3, 2)
        except Exception:
            logger.exception('Could not calculate storage usage')
        return {'used_gb': storage_used_gb, 'total_gb': storage_total_gb}

    def get_dashboard_stats(self) -> Dict[str, Any]:
        """Get all dashboard statistics."""
        user_counts = self.get_user_counts()
        message_counts = self.get_message_counts()
        error_counts = self.get_error_counts()
        storage_stats = self.get_storage_stats()
        return {'users': {'total': user_counts['total'], 'active_today': user_counts['active_today'], 'active_week': user_counts['active_week'], 'new_this_month': user_counts['new_this_month']}, 'tts': {'requests_today': message_counts['today'], 'requests_week': message_counts['week'], 'requests_month': message_counts['month']}, 'system': {'errors_24h': error_counts['errors_24h'], 'storage_used_gb': storage_stats['used_gb'], 'storage_total_gb': storage_stats['total_gb']}}

    def get_admin_list_stats(self) -> Dict[str, Any]:
        """Get statistics for admin list view."""
        user_counts = self.get_user_counts()
        message_counts = self.get_message_counts()
        channels = self.get_active_channels()
        return {'stats': {'total_users': user_counts['total'], 'active_users': user_counts['active'], 'total_messages': message_counts['total'], 'active_channels': len(channels)}, 'channels': channels}

    def get_monitoring_metrics(self) -> Dict[str, Any]:
        """Get monitoring metrics."""
        user_counts = self.get_user_counts()
        message_counts = self.get_message_counts()
        session_counts = self.get_session_counts()
        integration_counts = self.get_integration_counts()
        return {'users': {'total': user_counts['total'], 'active': user_counts['active'], 'blocked': user_counts['blocked']}, 'messages': {'last_24h': message_counts['last_24h'], 'last_1h': message_counts['last_1h']}, 'sessions': session_counts, 'integrations': {'active': integration_counts['total'], 'twitch': integration_counts['twitch'], 'vk': integration_counts['vk']}}

    def get_analytics(self) -> Dict[str, Any]:
        """Get analytics data."""
        hour_ago = utcnow_naive() - timedelta(hours=1)
        return {'active_users': self.repo.count_active_users_since(hour_ago), 'total_messages': self.repo.count_messages(), 'recent_messages': self.repo.count_messages(hour_ago), 'tts_requests': self.get_tts_stats()['enabled_users'], 'top_commands': self.get_top_commands(), 'timestamp': utcnow_naive().isoformat()}

    def get_admin_users_list(self, page: int=1, limit: int=50, search: str=None) -> Dict[str, Any]:
        """Get paginated user list with integrations and whitelist status."""
        offset = (page - 1) * limit
        (users, total) = self.repo.get_users_paginated(limit, offset, search)
        user_ids = [u.id for u in users]
        tokens = self.repo.get_active_tokens_for_users(user_ids)
        tokens_map = {}
        for t in tokens:
            key = (t.user_id, t.platform)
            tokens_map[key] = t
        usernames = []
        for u in users:
            if u.twitch_username:
                usernames.append(u.twitch_username.lower())
            if u.vk_username:
                usernames.append(u.vk_username.lower())
        whitelist_entries = self.repo.get_whitelisted_channels_by_names(usernames)
        whitelist_map = {(w.channel_name, w.platform): True for w in whitelist_entries}
        user_data = []
        for u in users:
            twitch_token = tokens_map.get((u.id, 'twitch'))
            vk_token = tokens_map.get((u.id, 'vk'))
            twitch_connected = twitch_token is not None and twitch_token.is_active
            vk_connected = vk_token is not None and vk_token.is_active
            twitch_display = u.twitch_username or (twitch_token.platform_user_id if twitch_token else None)
            vk_display = u.vk_username or u.vk_channel_name or (vk_token.platform_user_id if vk_token else None)
            whitelisted_platforms = []
            whitelisted_channels = {}
            if u.twitch_username and whitelist_map.get((u.twitch_username.lower(), 'twitch')):
                whitelisted_platforms.append('twitch')
                whitelisted_channels['twitch'] = u.twitch_username
            if u.vk_username and whitelist_map.get((u.vk_username.lower(), 'vk')):
                whitelisted_platforms.append('vk')
                whitelisted_channels['vk'] = u.vk_username
            user_data.append({'id': u.id, 'is_admin': bool(u.role == 'admin' or u.is_admin), 'is_active': u.is_active, 'is_blocked': u.is_blocked, 'blocked_reason': u.blocked_reason, 'created_at': u.created_at.isoformat() if u.created_at else None, 'twitch_username': u.twitch_username, 'vk_username': u.vk_username, 'vk_channel_name': u.vk_channel_name, 'integrations': {'twitch': {'connected': twitch_connected, 'username': twitch_display, 'enabled': twitch_connected}, 'vk': {'connected': vk_connected, 'username': vk_display, 'enabled': vk_connected}}, 'total_integrations': (1 if twitch_connected else 0) + (1 if vk_connected else 0), 'is_whitelisted': len(whitelisted_platforms) > 0, 'whitelisted_platforms': whitelisted_platforms, 'whitelisted_channels': whitelisted_channels})
        return {'users': user_data, 'pagination': {'page': page, 'limit': limit, 'total': total, 'total_users': total, 'pages': (total + limit - 1) // limit}}

    def get_sessions_paginated(self, page: int=1, limit: int=50) -> Dict[str, Any]:
        """Get paginated session list with user info."""
        offset = (page - 1) * limit
        sessions = self.repo.get_sessions_paginated(limit, offset)
        total = self.repo.count_all_sessions()
        user_ids = list({s.user_id for s in sessions if s.user_id})
        users_map = {}
        if user_ids:
            users = self.repo.get_users_by_ids(user_ids)
            users_map = {u.id: u for u in users}
        sessions_data = []
        for s in sessions:
            session_user = users_map.get(s.user_id)
            sessions_data.append({'id': s.id, 'user_id': s.user_id, 'username': session_user.twitch_username if session_user else 'Unknown', 'session_id': s.session_id, 'created_at': s.created_at.isoformat() if s.created_at else None, 'last_activity': s.last_activity.isoformat() if s.last_activity else None, 'is_active': s.is_active})
        return {'sessions': sessions_data, 'pagination': {'page': page, 'limit': limit, 'total': total, 'pages': (total + limit - 1) // limit}}

    def get_user_details(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific user."""
        (user, settings) = self.repo.get_user_with_settings(user_id)
        if not user:
            return None
        sessions_count = self.repo.count_user_active_sessions(user_id)
        message_count = self.repo.count_user_messages(user_id)
        return {'user': {'id': user.id, 'role': user.role, 'is_admin': bool(user.role == 'admin' or user.is_admin), 'is_active': user.is_active, 'is_blocked': user.is_blocked, 'twitch_username': user.twitch_username, 'vk_username': user.vk_username, 'vk_channel_name': user.vk_channel_name, 'created_at': user.created_at.isoformat() if user.created_at else None, 'blocked_at': user.blocked_at.isoformat() if user.blocked_at else None, 'blocked_reason': user.blocked_reason, 'tts_enabled': user.tts_enabled, 'tts_listening_mode': user.tts_listening_mode, 'twitch_is_broadcaster': user.twitch_is_broadcaster, 'twitch_is_moderator': user.twitch_is_moderator, 'twitch_is_vip': getattr(user, 'twitch_is_vip', False), 'twitch_is_subscriber': getattr(user, 'twitch_is_subscriber', False), 'vk_is_owner': user.vk_is_owner, 'vk_is_moderator': user.vk_is_moderator}, 'settings': {'chat_enabled': settings.chat_enabled if settings else False, 'channel_name': settings.channel_name if settings else None, 'vk_channel_name': settings.vk_channel_name if settings else None} if settings else None, 'stats': {'active_sessions': sessions_count, 'total_messages': message_count}}

def get_admin_stats_service(db: Session) -> AdminStatsService:
    return AdminStatsService(db)
