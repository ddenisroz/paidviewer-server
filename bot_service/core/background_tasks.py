"""Background task scheduler."""
import asyncio
import logging
from datetime import timedelta

from core.connection_manager import get_connection_manager
from core.database import User, get_db
from core.datetime_utils import utcnow_naive

logger = logging.getLogger(__name__)


class BackgroundTasks:
    """Manage long-running background tasks."""

    def __init__(self):
        self.tasks = []

    async def cleanup_old_chat_messages(self):
        """
        Clean up chat messages based on configured limits.

        This task removes only the oldest messages when hard limits are exceeded:
        - ``MAX_CHAT_MESSAGES_PER_USER`` per user
        - ``MAX_TOTAL_CHAT_MESSAGES`` across the database

        It does not delete messages by age. ``CHAT_MESSAGES_RETENTION_DAYS`` is used only
        for reporting and diagnostics.
        """
        while True:
            await asyncio.sleep(3600)

            try:
                db = next(get_db())
                try:
                    from services.database_cleanup_service import DatabaseCleanupService

                    cleanup_service = DatabaseCleanupService(db)
                    stats_before = cleanup_service.get_database_stats()
                    total_before = stats_before.get("total_chat_messages", 0)
                    cleanup_stats = cleanup_service.cleanup_old_data()
                    deleted_count = cleanup_stats.get("messages_deleted", 0)

                    if deleted_count > 0:
                        logger.info(
                            "[CHAT CLEANUP] Deleted %s old messages (total before cleanup: %s)",
                            deleted_count,
                            total_before,
                        )
                    else:
                        logger.debug("[CHAT CLEANUP] No messages exceeded cleanup limits")
                except Exception as e:
                    logger.error("[CHAT CLEANUP] Error in cleanup_old_chat_messages: %s", e)
                finally:
                    db.close()
            except Exception as e:
                logger.error("[CHAT CLEANUP] Critical error in cleanup task: %s", e)
                await asyncio.sleep(300)

    async def cleanup_expired_sessions(self):
        """Run retention cleanup for old inactive sessions."""
        while True:
            await asyncio.sleep(300)
            db = None
            try:
                db = next(get_db())
                from services.database_cleanup_service import DatabaseCleanupService

                cleanup_service = DatabaseCleanupService(db)
                cleanup_result = cleanup_service.cleanup_inactive_sessions(days_old=7)
                deleted_sessions = cleanup_result.get("deleted_sessions", 0)

                if deleted_sessions:
                    logger.info(
                        "[SESSION CLEANUP] Deleted %s inactive sessions older than %s days",
                        deleted_sessions,
                        cleanup_result.get("retention_days", 7),
                    )
            except Exception as e:
                logger.error("Error in cleanup_expired_sessions: %s", e)
            finally:
                if db is not None:
                    db.close()

    async def refresh_bot_oauth_tokens(self):
        """Refresh Twitch and VK bot OAuth tokens on a schedule."""
        while True:
            try:
                await asyncio.sleep(60 * 60)
                logger.info("[BOT TOKEN] Checking bot OAuth tokens")

                try:
                    from services.twitch_bot_oauth_service import twitch_bot_oauth_service
                    from services.vk_bot_oauth_service import vk_bot_oauth_service

                    await twitch_bot_oauth_service.refresh_if_needed()
                    await vk_bot_oauth_service.refresh_if_needed()
                except Exception as e:
                    logger.error("[BOT TOKEN] Error refreshing bot OAuth tokens: %s", e)
            except Exception as e:
                logger.error("[BOT TOKEN] Error in refresh loop: %s", e)
                await asyncio.sleep(60)

    async def cleanup_task(self):
        """Clean up inactive channels and clients."""
        while True:
            try:
                await asyncio.sleep(60)
                connection_manager = get_connection_manager()
                await connection_manager.cleanup_inactive_channels()
                await connection_manager.cleanup_inactive_clients()
            except Exception as e:
                logger.error("Error in cleanup task: %s", e)

    async def cleanup_deleted_accounts(self):
        """
        Permanently delete accounts 30 days after soft deletion.

        This satisfies the delayed-delete policy used for GDPR-style account removal.
        """
        while True:
            await asyncio.sleep(86400)

            try:
                db = next(get_db())
                try:
                    thirty_days_ago = utcnow_naive() - timedelta(days=30)

                    deleted_users = (
                        db.query(User)
                        .filter(
                            User.is_blocked,
                            User.blocked_reason == "account_deleted",
                            User.blocked_at < thirty_days_ago,
                        )
                        .all()
                    )

                    if deleted_users:
                        logger.info(
                            "[ACCOUNT CLEANUP] Found %s accounts scheduled for permanent deletion",
                            len(deleted_users),
                        )

                        for user in deleted_users:
                            try:
                                user_id = user.id
                                username = user.twitch_username or user.vk_username or f"user_{user_id}"
                                blocked_date = user.blocked_at

                                db.delete(user)
                                db.commit()

                                logger.info(
                                    "[ACCOUNT CLEANUP] Permanently deleted user %s (%s), blocked at %s",
                                    user_id,
                                    username,
                                    blocked_date,
                                )
                            except Exception as e:
                                logger.error("[ACCOUNT CLEANUP] Error deleting user %s: %s", user.id, e)
                                db.rollback()
                    else:
                        logger.debug("[ACCOUNT CLEANUP] No accounts scheduled for permanent deletion")
                except Exception as e:
                    logger.error("[ACCOUNT CLEANUP] Error in cleanup_deleted_accounts: %s", e)
                finally:
                    db.close()
            except Exception as e:
                logger.error("[ACCOUNT CLEANUP] Critical error in cleanup task: %s", e)
                await asyncio.sleep(3600)

    async def refresh_user_oauth_tokens(self):
        """
        Proactively refresh user OAuth tokens.

        The task checks every two hours and refreshes tokens that are already expired
        or will expire within the next hour.
        """
        from core.database import SessionLocal, UserToken
        from services.token_refresh_service import token_refresh_service

        first_run = True
        while True:
            try:
                if not first_run:
                    await asyncio.sleep(7200)
                else:
                    first_run = False
                    logger.info("[TOKEN REFRESH] Running initial token check on startup")

                logger.info("[TOKEN REFRESH] Checking for expired or expiring user OAuth tokens")

                db = SessionLocal()
                try:
                    now = utcnow_naive()
                    threshold = now + timedelta(hours=1)

                    expiring_tokens = (
                        db.query(UserToken)
                        .filter(
                            UserToken.expires_at.isnot(None),
                            UserToken.expires_at <= threshold,
                            UserToken.refresh_token.isnot(None),
                        )
                        .all()
                    )

                    if not expiring_tokens:
                        logger.debug("[TOKEN REFRESH] No expiring tokens found")
                    else:
                        logger.info("[TOKEN REFRESH] Found %s expiring tokens", len(expiring_tokens))

                    for token in expiring_tokens:
                        try:
                            logger.info(
                                "[TOKEN REFRESH] Refreshing %s token for user %s",
                                token.platform,
                                token.user_id,
                            )
                            success = await token_refresh_service._refresh_token(token, db)

                            if success:
                                logger.info(
                                    "[TOKEN REFRESH] Successfully refreshed %s token for user %s",
                                    token.platform,
                                    token.user_id,
                                )
                            else:
                                logger.error(
                                    "[TOKEN REFRESH] Failed to refresh %s token for user %s",
                                    token.platform,
                                    token.user_id,
                                )

                            await asyncio.sleep(1)
                        except Exception as e:
                            logger.error(
                                "[TOKEN REFRESH] Error refreshing token for user %s: %s",
                                token.user_id,
                                e,
                            )
                finally:
                    db.close()
            except Exception as e:
                logger.error("[TOKEN REFRESH] Error in token refresh task: %s", e)
                await asyncio.sleep(60)

    async def start_all_tasks(self):
        """Start all background tasks."""
        self.tasks = [
            asyncio.create_task(self.cleanup_old_chat_messages()),
            asyncio.create_task(self.cleanup_expired_sessions()),
            asyncio.create_task(self.refresh_bot_oauth_tokens()),
            asyncio.create_task(self.refresh_user_oauth_tokens()),
            asyncio.create_task(self.cleanup_task()),
            asyncio.create_task(self.cleanup_deleted_accounts()),
        ]

        logger.info("[BACKGROUND] Started 6 background tasks")
        logger.info("  - cleanup_old_chat_messages (every 1 hour)")
        logger.info("  - cleanup_expired_sessions (every 5 minutes)")
        logger.info("  - refresh_bot_oauth_tokens (every 1 hour)")
        logger.info("  - refresh_user_oauth_tokens (every 2 hours)")
        logger.info("  - cleanup_task (every 1 minute)")
        logger.info("  - cleanup_deleted_accounts (every 24 hours)")

    async def stop_all_tasks(self):
        """Stop all background tasks."""
        for task in self.tasks:
            task.cancel()

        await asyncio.gather(*self.tasks, return_exceptions=True)
        logger.info("Background tasks stopped")


background_tasks = BackgroundTasks()
