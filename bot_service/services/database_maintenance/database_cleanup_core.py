# services/database_maintenance/database_cleanup_core.py
"""Service for core database cleanup logic."""

import logging
from datetime import timedelta
from typing import Dict, Any
from pathlib import Path

from sqlalchemy.orm import Session
from sqlalchemy import and_, delete, func, select

from core.database import User
from models import (
    AudioSettings,
    BotCommand,
    ChatBoxSettings,
    DropsConfig,
    DropsHistory,
    DropsReward,
    FilteredWord,
    LocalTTSEndpoint,
    MythicalDropsSession,
    StreamSession,
    TTSBlockedUser,
    TTSUserSettings,
    UserSession,
    UserSettings,
    UserStreak,
    UserToken,
    UserVoiceSettings,
    YouTubeQueue,
)
from core.datetime_utils import utcnow_naive
from repositories.database_stats_repository import DatabaseStatsRepository

logger = logging.getLogger(__name__)


class DatabaseCleanupCore:
    """Service for core cleanup logic"""

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
        self.repo_root = Path(__file__).resolve().parents[3]

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

    def _orphan_cleanup_models(self) -> list[tuple[str, object]]:
        """Return user-owned tables that may contain orphaned ``user_id`` rows."""
        return [
            ("user_settings", UserSettings),
            ("tts_user_settings", TTSUserSettings),
            ("audio_settings", AudioSettings),
            ("user_voice_settings", UserVoiceSettings),
            ("local_tts_endpoints", LocalTTSEndpoint),
            ("filtered_words", FilteredWord),
            ("tts_blocked_users", TTSBlockedUser),
            ("user_tokens", UserToken),
            ("youtube_queue", YouTubeQueue),
            ("drops_configs", DropsConfig),
            ("drops_rewards", DropsReward),
            ("user_streaks", UserStreak),
            ("drops_history", DropsHistory),
            ("mythical_drops_sessions", MythicalDropsSession),
            ("stream_sessions", StreamSession),
            ("chatbox_settings", ChatBoxSettings),
            ("bot_commands", BotCommand),
        ]

    def _orphan_user_condition(self, model: object) -> object:
        """Build a correlated condition for rows whose ``user_id`` no longer exists."""
        return and_(
            model.user_id.is_not(None),
            ~select(User.id).where(User.id == model.user_id).exists(),
        )

    def _legacy_session_scope_models(self) -> list[tuple[str, object]]:
        """Return active user-only tables that should no longer keep session-scoped rows."""
        return [
            ("user_settings", UserSettings),
            ("tts_user_settings", TTSUserSettings),
            ("local_tts_endpoints", LocalTTSEndpoint),
            ("filtered_words", FilteredWord),
            ("tts_blocked_users", TTSBlockedUser),
            ("youtube_queue", YouTubeQueue),
            ("drops_configs", DropsConfig),
            ("drops_rewards", DropsReward),
            ("user_streaks", UserStreak),
            ("drops_history", DropsHistory),
            ("mythical_drops_sessions", MythicalDropsSession),
            ("stream_sessions", StreamSession),
        ]

    def _legacy_session_scope_condition(self, model: object) -> object:
        """Build a condition for legacy session-scoped rows in user-only tables."""
        return and_(
            model.user_id.is_(None),
            model.session_id.is_not(None),
        )

    def cleanup_old_data(self) -> Dict[str, int]:
        """Clean old data: expired messages and over-limit messages."""
        try:
            cleanup_stats = {
                'messages_deleted': 0,
                'old_messages_deleted': 0,
                'limit_based_deleted': 0,
                'users_cleaned': 0,
                'cleanup_reason': 'age_and_limit_based'
            }

            # 1. Delete messages older than retention period via repository
            old_messages_count = self.stats_repo.delete_old_messages(
                self.CHAT_MESSAGES_RETENTION_DAYS
            )
            if old_messages_count > 0:
                cleanup_stats['old_messages_deleted'] = old_messages_count
                cleanup_stats['messages_deleted'] += old_messages_count
                logger.info(f"[DELETE] Deleted {old_messages_count} messages older than {self.CHAT_MESSAGES_RETENTION_DAYS} days")

            # 2. Delete excess messages if total limit exceeded
            total_messages = self.stats_repo.count_total_messages()
            if total_messages > self.MAX_TOTAL_CHAT_MESSAGES:
                excess_count = total_messages - self.MAX_TOTAL_CHAT_MESSAGES
                # Get oldest message IDs and delete them
                oldest_ids = self.stats_repo.get_oldest_messages_ids(excess_count)
                deleted = self.stats_repo.delete_messages_by_ids(oldest_ids)
                cleanup_stats['limit_based_deleted'] = deleted
                cleanup_stats['messages_deleted'] += deleted
                logger.info(f"[DELETE] Deleted {deleted} excess messages to maintain total limit ({self.MAX_TOTAL_CHAT_MESSAGES})")

            # 3. Clean excess messages per user via repository
            user_cleanup_count = self._cleanup_user_message_limits()
            cleanup_stats['limit_based_deleted'] += user_cleanup_count
            cleanup_stats['messages_deleted'] += user_cleanup_count

            if cleanup_stats['messages_deleted'] == 0:
                logger.info("[OK] No messages deleted - all within limits and retention period")
            else:
                logger.info(f"[OK] Cleanup completed: {cleanup_stats['messages_deleted']} messages deleted "
                          f"(old: {cleanup_stats['old_messages_deleted']}, limit-based: {cleanup_stats['limit_based_deleted']})")

            return cleanup_stats

        except Exception:
            logger.exception("[ERROR] Error cleaning up old data")
            self.db.rollback()
            return {'messages_deleted': 0, 'old_messages_deleted': 0, 'limit_based_deleted': 0, 'users_cleaned': 0, 'error': "Internal server error"}

    def _cleanup_user_message_limits(self) -> int:
        """Clean excess messages for users over limit."""
        try:
            total_deleted = 0

            # Get users over limit via repository
            user_message_counts = self.stats_repo.get_user_message_counts_over_limit(
                self.MAX_CHAT_MESSAGES_PER_USER
            )

            for user_id, message_count in user_message_counts:
                excess_count = message_count - self.MAX_CHAT_MESSAGES_PER_USER

                # Get and delete oldest messages for this user
                oldest_messages = self.stats_repo.get_oldest_messages_for_user(user_id, excess_count)
                if oldest_messages:
                    message_ids = [m.id for m in oldest_messages]
                    deleted_count = self.stats_repo.delete_messages_by_ids(message_ids)
                    total_deleted += deleted_count
                    logger.info(f"Deleted {deleted_count} excess messages for user {user_id} (limit: {self.MAX_CHAT_MESSAGES_PER_USER})")

            return total_deleted

        except Exception:
            logger.exception("Error cleaning up user message limits")
            return 0

    def preview_orphan_user_records(self) -> Dict[str, Any]:
        """Preview orphaned user-owned rows that reference missing users."""
        try:
            counts: Dict[str, int] = {}
            for table_name, model in self._orphan_cleanup_models():
                condition = self._orphan_user_condition(model)
                counts[table_name] = int(
                    self.db.execute(
                        select(func.count()).select_from(model).where(condition)
                    ).scalar_one()
                )

            total_rows = sum(counts.values())
            return {
                "tables": counts,
                "total_rows": total_rows,
            }
        except Exception:
            logger.exception("Error previewing orphan user records")
            self.db.rollback()
            return {"tables": {}, "total_rows": 0, "error": "Internal server error"}

    def cleanup_orphan_user_records(self) -> Dict[str, Any]:
        """Delete orphaned user-owned rows that reference missing users."""
        try:
            deleted_counts: Dict[str, int] = {}

            for table_name, model in self._orphan_cleanup_models():
                condition = self._orphan_user_condition(model)
                result = self.db.execute(delete(model).where(condition))
                deleted_counts[table_name] = int(result.rowcount or 0)

            total_rows = sum(deleted_counts.values())
            self.db.commit()

            if total_rows:
                logger.info(
                    "[DB CLEANUP] Deleted %s orphan user-owned rows: %s",
                    total_rows,
                    {name: count for name, count in deleted_counts.items() if count},
                )
            else:
                logger.info("[DB CLEANUP] No orphan user-owned rows found")

            return {
                "tables": deleted_counts,
                "total_rows": total_rows,
            }
        except Exception:
            logger.exception("Error cleaning orphan user records")
            self.db.rollback()
            return {"tables": {}, "total_rows": 0, "error": "Internal server error"}

    def preview_legacy_session_records(self) -> Dict[str, Any]:
        """Preview legacy session-scoped rows in active user-only tables."""
        try:
            counts: Dict[str, int] = {}
            for table_name, model in self._legacy_session_scope_models():
                condition = self._legacy_session_scope_condition(model)
                counts[table_name] = int(
                    self.db.execute(
                        select(func.count()).select_from(model).where(condition)
                    ).scalar_one()
                )

            total_rows = sum(counts.values())
            return {
                "tables": counts,
                "total_rows": total_rows,
            }
        except Exception:
            logger.exception("Error previewing legacy session-scoped records")
            self.db.rollback()
            return {"tables": {}, "total_rows": 0, "error": "Internal server error"}

    def cleanup_legacy_session_records(self) -> Dict[str, Any]:
        """Delete legacy session-scoped rows from active user-only tables."""
        try:
            deleted_counts: Dict[str, int] = {}

            for table_name, model in self._legacy_session_scope_models():
                condition = self._legacy_session_scope_condition(model)
                result = self.db.execute(delete(model).where(condition))
                deleted_counts[table_name] = int(result.rowcount or 0)

            total_rows = sum(deleted_counts.values())
            self.db.commit()

            if total_rows:
                logger.info(
                    "[DB CLEANUP] Deleted %s legacy session-scoped rows: %s",
                    total_rows,
                    {name: count for name, count in deleted_counts.items() if count},
                )
            else:
                logger.info("[DB CLEANUP] No legacy session-scoped rows found")

            return {
                "tables": deleted_counts,
                "total_rows": total_rows,
            }
        except Exception:
            logger.exception("Error cleaning legacy session-scoped records")
            self.db.rollback()
            return {"tables": {}, "total_rows": 0, "error": "Internal server error"}

    def preview_inactive_session_cleanup(self, days_old: int = 7) -> Dict[str, int]:
        """Preview inactive session retention cleanup."""
        try:
            cutoff_date = utcnow_naive() - timedelta(days=days_old)
            total_sessions = int(
                self.db.execute(select(func.count()).select_from(UserSession)).scalar_one()
            )
            active_sessions = int(
                self.db.execute(
                    select(func.count()).select_from(UserSession).where(UserSession.is_active.is_(True))
                ).scalar_one()
            )
            old_inactive_sessions = int(
                self.db.execute(
                    select(func.count())
                    .select_from(UserSession)
                    .where(
                        UserSession.is_active.is_(False),
                        UserSession.last_activity < cutoff_date,
                    )
                ).scalar_one()
            )
            return {
                "retention_days": days_old,
                "total_sessions": total_sessions,
                "active_sessions": active_sessions,
                "inactive_sessions": total_sessions - active_sessions,
                "old_inactive_sessions": old_inactive_sessions,
            }
        except Exception:
            logger.exception("Error previewing inactive session cleanup")
            self.db.rollback()
            return {
                "retention_days": days_old,
                "total_sessions": 0,
                "active_sessions": 0,
                "inactive_sessions": 0,
                "old_inactive_sessions": 0,
                "error": "Internal server error",
            }

    def cleanup_inactive_sessions(self, days_old: int = 7) -> Dict[str, int]:
        """Delete inactive sessions older than the retention window."""
        try:
            cutoff_date = utcnow_naive() - timedelta(days=days_old)
            result = self.db.execute(
                delete(UserSession).where(
                    UserSession.is_active.is_(False),
                    UserSession.last_activity < cutoff_date,
                )
            )
            deleted_count = int(result.rowcount or 0)
            self.db.commit()

            if deleted_count:
                logger.info(
                    "[DB CLEANUP] Deleted %s inactive sessions older than %s days",
                    deleted_count,
                    days_old,
                )
            else:
                logger.debug(
                    "[DB CLEANUP] No inactive sessions older than %s days found",
                    days_old,
                )

            return {
                "retention_days": days_old,
                "deleted_sessions": deleted_count,
            }
        except Exception:
            logger.exception("Error cleaning inactive sessions")
            self.db.rollback()
            return {
                "retention_days": days_old,
                "deleted_sessions": 0,
                "error": "Internal server error",
            }

    def cleanup_user_data(self, username: str, platform: str, keep_days: int = 30) -> int:
        """Clean old data for a specific user."""
        try:
            from repositories.user_repository import UserRepository
            from repositories.chat_message_repository import ChatMessageRepository
            
            user_repo = UserRepository(self.db)
            user = user_repo.get_by_id(int(username))
            if not user:
                return 0

            # Use repository for message operations
            msg_repo = ChatMessageRepository(self.db)
            cutoff_date = utcnow_naive() - timedelta(days=keep_days)
            
            count = msg_repo.delete_old_by_user_platform(user.id, platform, cutoff_date)
            
            if count > 0:
                self.db.commit()
                logger.info(f"Cleaned {count} old messages for user {username}")

            return count

        except Exception:
            logger.exception("Error cleaning user data")
            self.db.rollback()
            return 0

    def cleanup_cache(self) -> Dict[str, Any]:
        """Clean cache files."""
        try:
            import pathlib

            deleted_files = 0
            freed_space = 0

            for cache_dir in self._cache_dirs():
                if not cache_dir.exists():
                    continue

                try:
                    for cache_file in pathlib.Path(cache_dir).glob('**/*'):
                        if cache_file.is_file():
                            try:
                                freed_space += cache_file.stat().st_size
                                cache_file.unlink()
                                deleted_files += 1
                            except Exception:
                                logger.exception("Could not delete cache file %s", cache_file)
                except Exception:
                    logger.exception("Error cleaning cache directory %s", cache_dir)

            logger.info(f"[DB] Cache cleaned: {deleted_files} files removed, freed {freed_space / (1024*1024):.2f} MB")
            return {
                'deleted_files': deleted_files,
                'freed_space_bytes': freed_space
            }

        except Exception:
            logger.exception("Error cleaning cache")
            return {'deleted_files': 0, 'freed_space_bytes': 0, 'error': "Internal server error"}

    def sync_user_message_counts(self) -> Dict[str, int]:
        """Sync user message counters with actual DB data."""
        try:
            from core.database import UserProgression
            from repositories.chat_message_repository import ChatMessageRepository

            sync_stats = {
                'users_updated': 0,
                'total_discrepancies': 0
            }

            # Note: UserProgression query stays here as it's a maintenance-only table
            # Could be moved to a dedicated MaintenanceRepository in the future
            progressions = self.db.query(UserProgression).all()
            msg_repo = ChatMessageRepository(self.db)

            for progression in progressions:
                # Count actual messages using repository
                real_count = msg_repo.count_by_user_channel_platform(
                    progression.user_id, 
                    progression.channel_name, 
                    progression.platform
                )

                if progression.total_messages != real_count:
                    discrepancy = abs(progression.total_messages - real_count)
                    progression.total_messages = real_count
                    sync_stats['users_updated'] += 1
                    sync_stats['total_discrepancies'] += discrepancy
                    logger.info(f"Synced message count for user {progression.user_id} in {progression.channel_name}: {real_count}")

            if sync_stats['users_updated'] > 0:
                self.db.commit()
                logger.info(f"Message count sync completed: {sync_stats}")

            return sync_stats

        except Exception:
            logger.exception("Error syncing user message counts")
            self.db.rollback()
            return {}

    def get_user_message_count(self, username: str, platform: str) -> int:
        """Get message count for a user."""
        try:
            from repositories.user_repository import UserRepository
            from repositories.chat_message_repository import ChatMessageRepository
            
            user_repo = UserRepository(self.db)
            user = user_repo.get_by_id(int(username))
            if not user:
                return 0

            msg_repo = ChatMessageRepository(self.db)
            return msg_repo.count_by_user_platform(user.id, platform)

        except Exception:
            logger.exception("Error getting user message count")
            return 0
