# services/database_maintenance/database_stats_service.py
"""Service for gathering database statistics - refactored to use repositories."""

import logging
import os
from typing import Dict, Any
from pathlib import Path

from sqlalchemy.orm import Session

from repositories.database_stats_repository import DatabaseStatsRepository

logger = logging.getLogger(__name__)


class DatabaseStatsService:
    """Service for gathering database statistics"""

    def __init__(self, db: Session):
        self.db = db
        self.stats_repo = DatabaseStatsRepository(db)
        
        # Settings from config
        from core.config import settings
        self.MAX_CHAT_MESSAGES_PER_USER = settings.chat_messages_db_limit_per_user
        self.MAX_TOTAL_CHAT_MESSAGES = settings.chat_messages_db_limit_total
        self.CHAT_MESSAGES_RETENTION_DAYS = settings.chat_messages_retention_days
        storage_root = (settings.f5_tts_storage_root or "").strip()
        self.f5_storage_root = Path(storage_root).expanduser() if storage_root else None
        
        # Psychology analyses no longer stored in DB
        self.MAX_PSYCHOLOGY_ANALYSES = 0
        self.PSYCHOLOGY_RETENTION_DAYS = 0
        self.repo_root = Path(__file__).resolve().parents[3]

    def _resolve_voices_dir(self) -> Path:
        """Resolve active voices directory in split-deployment friendly layouts."""
        candidates = []
        if self.f5_storage_root:
            candidates.extend(
                [
                    self.f5_storage_root / 'audio' / 'voices' / 'user',
                    self.f5_storage_root / 'user_voices',
                ]
            )

        candidates.extend(
            [
                self.repo_root / 'audio' / 'voices' / 'user',
                self.repo_root / 'user_voices',
            ]
        )
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    def _cache_dirs(self) -> list[Path]:
        """Return known cache directories for current project layout."""
        cache_dirs = [
            self.repo_root / '.cache',
            self.repo_root / 'temp',
            self.repo_root / 'audio' / 'cache',
        ]
        if self.f5_storage_root:
            cache_dirs.append(self.f5_storage_root / 'audio' / 'cache')
        return cache_dirs

    def get_database_stats(self) -> Dict[str, Any]:
        """Get database statistics using repository pattern."""
        try:
            stats = {}

            # Message statistics via repository
            total_messages = self.stats_repo.count_total_messages()
            stats['total_chat_messages'] = total_messages

            # Platform statistics via repository
            twitch_messages = self.stats_repo.count_messages_by_platform('twitch')
            vk_messages = self.stats_repo.count_messages_by_platform('vk')
            stats['twitch_messages'] = twitch_messages
            stats['vk_messages'] = vk_messages

            # Psychology analyses no longer stored in DB
            stats['total_psychology_analyses'] = 0

            # User statistics via repository
            total_users = self.stats_repo.count_total_users()
            stats['total_users'] = total_users

            # Database size via repository
            database_size_bytes = self.stats_repo.get_database_size_bytes()
            stats['database_size_bytes'] = database_size_bytes
            stats['estimated_db_size_mb'] = round(database_size_bytes / (1024 * 1024), 2)

            # For frontend
            stats['total_records'] = total_messages + total_users

            # Component sizes (approximate)
            stats['logs_size_bytes'] = int(database_size_bytes * 0.3)
            stats['log_entries'] = total_messages

            stats['voices_size_bytes'] = self._get_voices_size()
            stats['voices_count'] = self._count_voice_files()

            stats['cache_size_bytes'] = self._get_cache_size()
            stats['cache_files'] = self._count_cache_files()

            stats['backup_size_bytes'] = self._get_latest_backup_size()
            stats['last_backup_time'] = self._get_latest_backup_time()

            # Old records via repository
            old_messages = self.stats_repo.count_old_messages(self.CHAT_MESSAGES_RETENTION_DAYS)
            stats['old_messages_to_cleanup'] = old_messages
            stats['old_analyses_to_cleanup'] = 0

            # Limits
            stats['max_messages_per_user'] = self.MAX_CHAT_MESSAGES_PER_USER
            stats['max_total_messages'] = self.MAX_TOTAL_CHAT_MESSAGES

            # Users over limit via repository
            users_over_limit = self.stats_repo.count_users_over_message_limit(
                self.MAX_CHAT_MESSAGES_PER_USER
            )
            stats['users_over_message_limit'] = users_over_limit

            return stats

        except Exception:
            logger.exception("Error getting database stats")
            return {}

    def _get_voices_size(self) -> int:
        """Get voices directory size in bytes."""
        try:
            voices_dir = self._resolve_voices_dir()
            if not voices_dir.exists():
                return 0
            total_size = 0
            for root, dirs, files in os.walk(voices_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    total_size += os.path.getsize(file_path)
            return total_size
        except Exception:
            logger.exception("Error getting voices size")
            return 0

    def _count_voice_files(self) -> int:
        """Count voice files in directory."""
        try:
            voices_dir = self._resolve_voices_dir()
            if not voices_dir.exists():
                return 0
            return len([f for f in os.listdir(voices_dir) if f.endswith('.wav')])
        except Exception:
            logger.exception("Error counting voice files")
            return 0

    def _get_cache_size(self) -> int:
        """Get cache directory size in bytes."""
        try:
            total_size = 0
            for cache_dir in self._cache_dirs():
                if not cache_dir.exists():
                    continue
                for root, dirs, files in os.walk(cache_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        total_size += os.path.getsize(file_path)
            return total_size
        except Exception:
            logger.exception("Error getting cache size")
            return 0

    def _count_cache_files(self) -> int:
        """Count files in cache directories."""
        try:
            total_count = 0
            for cache_dir in self._cache_dirs():
                if not cache_dir.exists():
                    continue
                total_count += sum(len(files) for _, _, files in os.walk(cache_dir))
            return total_count
        except Exception:
            logger.exception("Error counting cache files")
            return 0

    def _get_latest_backup_size(self) -> int:
        """Get latest backup size in bytes."""
        try:
            backup_dir = self.repo_root / 'backups'
            if not os.path.exists(backup_dir):
                return 0
            files = os.listdir(backup_dir)
            if not files:
                return 0
            latest_backup = sorted(files, key=lambda x: os.path.getmtime(os.path.join(backup_dir, x)))[-1]
            return os.path.getsize(os.path.join(backup_dir, latest_backup))
        except Exception:
            logger.exception("Error getting latest backup size")
            return 0

    def _get_latest_backup_time(self) -> str:
        """Get latest backup time."""
        try:
            from datetime import datetime
            backup_dir = self.repo_root / 'backups'
            if not os.path.exists(backup_dir):
                return None
            files = [f for f in os.listdir(backup_dir) if f.startswith('backup_') and (f.endswith('.db') or f.endswith('.sql'))]
            if not files:
                return None
            latest_backup = sorted(files, key=lambda x: os.path.getmtime(os.path.join(backup_dir, x)))[-1]
            timestamp = os.path.getmtime(os.path.join(backup_dir, latest_backup))
            return datetime.fromtimestamp(timestamp).isoformat()
        except Exception:
            logger.exception("Error getting latest backup time")
            return None
