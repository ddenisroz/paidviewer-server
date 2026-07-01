# services/database_cleanup_service.py
import logging
from typing import Any, Dict

from sqlalchemy.orm import Session

from core.datetime_utils import utcnow_naive
from services.database_maintenance.database_backup_service import DatabaseBackupService
from services.database_maintenance.database_cleanup_core import DatabaseCleanupCore
from services.database_maintenance.database_stats_service import DatabaseStatsService

logger = logging.getLogger(__name__)


class DatabaseCleanupService:
    """Facade service for database maintenance operations."""

    def __init__(self, db: Session):
        self.db = db
        self.stats_service = DatabaseStatsService(db)
        self.backup_service = DatabaseBackupService()
        self.cleanup_core = DatabaseCleanupCore(db)

    def get_database_stats(self) -> Dict[str, Any]:
        """Return aggregated database statistics."""
        return self.stats_service.get_database_stats()

    def cleanup_old_data(self) -> Dict[str, int]:
        """Delete old chat data by retention and message-count limits."""
        return self.cleanup_core.cleanup_old_data()

    def optimize_database(self) -> Dict[str, Any]:
        """Run the current optimization routine and return before/after stats."""
        try:
            stats_before = self.get_database_stats()
            cleanup_stats = self.cleanup_old_data()
            stats_after = self.get_database_stats()

            return {
                "before": stats_before,
                "after": stats_after,
                "cleanup": cleanup_stats,
                "optimization_date": utcnow_naive().isoformat(),
            }
        except Exception:
            logger.exception("Error optimizing database")
            return {}

    def create_backup(self) -> Dict[str, Any]:
        """Create a database backup."""
        return self.backup_service.create_backup()

    def restore_from_backup(self) -> Dict[str, Any]:
        """Restore the database from the latest backup."""
        return self.backup_service.restore_from_backup()

    def restore_from_backup_file(self, filename: str) -> Dict[str, Any]:
        """Restore the database from a specific backup file."""
        return self.backup_service.restore_from_backup_file(filename)

    def list_backups(self) -> Dict[str, Any]:
        """List available backup files."""
        return self.backup_service.list_backups()

    def delete_backup(self, filename: str) -> Dict[str, Any]:
        """Delete a specific backup file."""
        return self.backup_service.delete_backup(filename)

    def cleanup_cache(self) -> Dict[str, Any]:
        """Delete generated cache files."""
        return self.cleanup_core.cleanup_cache()

    def preview_orphan_user_records(self) -> Dict[str, Any]:
        """Preview orphaned user-owned rows that reference missing users."""
        return self.cleanup_core.preview_orphan_user_records()

    def cleanup_orphan_user_records(self) -> Dict[str, Any]:
        """Delete orphaned user-owned rows that reference missing users."""
        return self.cleanup_core.cleanup_orphan_user_records()

    def preview_legacy_session_records(self) -> Dict[str, Any]:
        """Preview legacy session-scoped rows in active user-only tables."""
        return self.cleanup_core.preview_legacy_session_records()

    def cleanup_legacy_session_records(self) -> Dict[str, Any]:
        """Delete legacy session-scoped rows in active user-only tables."""
        return self.cleanup_core.cleanup_legacy_session_records()

    def preview_inactive_session_cleanup(self, days_old: int = 7) -> Dict[str, int]:
        """Preview inactive sessions eligible for retention cleanup."""
        return self.cleanup_core.preview_inactive_session_cleanup(days_old)

    def cleanup_inactive_sessions(self, days_old: int = 7) -> Dict[str, int]:
        """Delete inactive sessions older than the retention window."""
        return self.cleanup_core.cleanup_inactive_sessions(days_old)

    def sync_user_message_counts(self) -> Dict[str, int]:
        """Synchronize persisted per-user message counters with actual chat data."""
        return self.cleanup_core.sync_user_message_counts()

    def get_user_message_count(self, username: str, platform: str) -> int:
        """Get the current message count for a user."""
        return self.cleanup_core.get_user_message_count(username, platform)

    def cleanup_user_data(self, username: str, platform: str, keep_days: int = 30) -> int:
        """Delete old messages for a specific user and platform."""
        return self.cleanup_core.cleanup_user_data(username, platform, keep_days)
