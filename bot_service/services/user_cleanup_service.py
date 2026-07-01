"""Safe hard-delete workflow for user cleanup and admin maintenance."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Tuple

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from core.database import User
from core.user_cache_invalidation import invalidate_user_cache

logger = logging.getLogger(__name__)


@dataclass
class UserDeletionPreview:
    """Dry-run preview for permanent user deletion."""

    user_id: int
    username: str
    role: str
    channel_names: List[str]
    platform_user_ids: List[str]
    counts: Dict[str, int]
    total_rows: int


@dataclass
class UserDeletionResult:
    """Result of a completed permanent deletion."""

    success: bool
    message: str
    deleted_counts: Dict[str, int]


DeletePlanStep = Tuple[str, object, object]


class UserCleanupService:
    """Builds previews and performs transactional permanent user cleanup."""

    def preview_user_deletion(self, user_id: int, db: Session) -> UserDeletionPreview:
        user = self._get_user_or_raise(user_id, db)
        preview, _ = self._build_delete_plan(user, db)
        return preview

    async def permanently_delete_user(
        self,
        user_id: int,
        db: Session,
        *,
        actor_user_id: int | None = None,
    ) -> UserDeletionResult:
        if actor_user_id is not None and actor_user_id == user_id:
            raise ValueError("Cannot permanently delete yourself")

        user = self._get_user_or_raise(user_id, db)
        preview, delete_plan = self._build_delete_plan(user, db)
        actor_label = f"admin {actor_user_id}" if actor_user_id else "maintenance script"
        deleted_counts: Dict[str, int] = {}

        try:
            await self._disconnect_all_bots(user)

            for table_name, model, condition in delete_plan:
                result = db.execute(delete(model).where(condition))
                deleted_counts[table_name] = int(result.rowcount or 0)

            result = db.execute(delete(User).where(User.id == user_id))
            deleted_counts["users"] = int(result.rowcount or 0)
            db.commit()

            invalidate_user_cache(user_id, "account permanently deleted")

            logger.info(
                "[USER CLEANUP] User %s (%s) permanently deleted by %s: %s",
                user_id,
                preview.username,
                actor_label,
                deleted_counts,
            )

            return UserDeletionResult(
                success=True,
                message=f"User {user_id} permanently deleted",
                deleted_counts=deleted_counts,
            )
        except Exception:
            db.rollback()
            logger.exception("[USER CLEANUP] Hard delete failed for user %s", user_id)
            raise

    async def _disconnect_all_bots(self, user: User) -> None:
        """Disconnect active bot bindings for the user's channels."""
        from core.connection_manager import get_connection_manager
        from startup.bot_registry import get_bot_registry

        connection_manager = get_connection_manager()
        registry = get_bot_registry()

        if user.twitch_username:
            connection_manager.disable_tts_for_channel(user.twitch_username.lower())
            logger.info("[USER CLEANUP] Disconnected Twitch bot from %s", user.twitch_username)

        channel_name = user.vk_channel_name or user.vk_username
        if channel_name:
            try:
                if registry.vk_bot:
                    await registry.vk_bot.disconnect_from_channel(channel_name)
                connection_manager.disable_tts_for_channel(channel_name.lower())
                logger.info("[USER CLEANUP] Disconnected VK bot from %s", channel_name)
            except Exception:
                logger.exception("[USER CLEANUP] Error disconnecting VK bot")

    def _get_user_or_raise(self, user_id: int, db: Session) -> User:
        from repositories.user_repository import UserRepository

        user = UserRepository(db).get_by_id(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        return user

    def _collect_channel_names(self, user: User) -> List[str]:
        names = {
            value.strip().lower()
            for value in (user.twitch_username, user.vk_username, user.vk_channel_name)
            if isinstance(value, str) and value.strip()
        }
        return sorted(names)

    def _collect_platform_user_ids(self, user_id: int, db: Session) -> List[str]:
        from models.user import UserToken

        rows = db.execute(
            select(UserToken.platform_user_id).where(UserToken.user_id == user_id)
        ).scalars()
        return sorted({str(value) for value in rows if value})

    def _build_delete_plan(
        self,
        user: User,
        db: Session,
    ) -> Tuple[UserDeletionPreview, List[DeletePlanStep]]:
        from models.analytics import ChatMessage, PsychologyAnalysis, UserProgression
        from models.commands import BotCommand
        from models.drops import (
            DropsConfig,
            DropsHistory,
            DropsReward,
            MemeAlertsGrantHistory,
            MythicalDropsSession,
            StreamSession,
            UserStreak,
        )
        from models.gamification import Achievement, DonationAlert, UserAchievement
        from models.moderation import BlockedChannel, WhitelistedChannel
        from models.points import ChannelPoints, ChannelReward, PointsTransaction, RewardQueue
        from models.security import SecurityLog, SystemLog
        from models.tts import (
            AudioSettings,
            FilteredWord,
            LocalTTSEndpoint,
            TTSBlockedUser,
            TTSUserSettings,
            UserVoiceSettings,
        )
        from models.user import AdminUser, UserSession, UserSettings, UserToken
        from models.worker import TTSJob, TTSJobAttempt, Worker, WorkerPairingToken
        from models.widgets import ChatBoxSettings
        from models.youtube import YouTubeQueue

        user_id = user.id
        channel_names = self._collect_channel_names(user)
        platform_user_ids = self._collect_platform_user_ids(user_id, db)
        worker_ids = list(
            db.execute(select(Worker.id).where(Worker.owner_user_id == user_id)).scalars()
        )
        job_conditions = [
            TTSJob.owner_user_id == user_id,
            TTSJob.created_by_user_id == user_id,
        ]
        if worker_ids:
            job_conditions.extend(
                [
                    TTSJob.target_worker_id.in_(worker_ids),
                    TTSJob.assigned_worker_id.in_(worker_ids),
                ]
            )
        job_ids = list(db.execute(select(TTSJob.id).where(or_(*job_conditions))).scalars())

        delete_plan: List[DeletePlanStep] = [
            ("security_logs", SecurityLog, SecurityLog.user_id == user_id),
            (
                "system_logs",
                SystemLog,
                or_(SystemLog.admin_id == user_id, SystemLog.target_user_id == user_id),
            ),
            (
                "psychology_analysis",
                PsychologyAnalysis,
                or_(
                    PsychologyAnalysis.target_user_id == user_id,
                    PsychologyAnalysis.analyzed_by_user_id == user_id,
                ),
            ),
            ("chat_messages", ChatMessage, ChatMessage.user_id == user_id),
            ("user_progression", UserProgression, UserProgression.user_id == user_id),
            ("user_achievements", UserAchievement, UserAchievement.user_id == user_id),
            ("donation_alerts", DonationAlert, DonationAlert.user_id == user_id),
            ("reward_queue", RewardQueue, RewardQueue.user_id == user_id),
            ("points_transactions", PointsTransaction, PointsTransaction.user_id == user_id),
            ("channel_points", ChannelPoints, ChannelPoints.user_id == user_id),
            ("channel_rewards", ChannelReward, ChannelReward.user_id == user_id),
            ("youtube_queue", YouTubeQueue, YouTubeQueue.user_id == user_id),
            ("user_streaks", UserStreak, UserStreak.user_id == user_id),
            ("drops_history", DropsHistory, DropsHistory.user_id == user_id),
            ("memealerts_grant_history", MemeAlertsGrantHistory, MemeAlertsGrantHistory.user_id == user_id),
            ("mythical_drops_sessions", MythicalDropsSession, MythicalDropsSession.user_id == user_id),
            ("stream_sessions", StreamSession, StreamSession.user_id == user_id),
            ("drops_rewards", DropsReward, DropsReward.user_id == user_id),
            ("drops_configs", DropsConfig, DropsConfig.user_id == user_id),
            ("user_voice_settings", UserVoiceSettings, UserVoiceSettings.user_id == user_id),
            ("audio_settings", AudioSettings, AudioSettings.user_id == user_id),
            ("local_tts_endpoints", LocalTTSEndpoint, LocalTTSEndpoint.user_id == user_id),
            ("worker_pairing_tokens", WorkerPairingToken, WorkerPairingToken.owner_user_id == user_id),
            ("filtered_words", FilteredWord, FilteredWord.user_id == user_id),
            ("tts_blocked_users", TTSBlockedUser, TTSBlockedUser.user_id == user_id),
            ("tts_user_settings", TTSUserSettings, TTSUserSettings.user_id == user_id),
            ("chatbox_settings", ChatBoxSettings, ChatBoxSettings.user_id == user_id),
            ("bot_commands", BotCommand, BotCommand.user_id == user_id),
            ("user_sessions", UserSession, UserSession.user_id == user_id),
            ("user_tokens", UserToken, UserToken.user_id == user_id),
            ("user_settings", UserSettings, UserSettings.user_id == user_id),
        ]

        if job_ids or worker_ids:
            attempt_conditions = []
            if job_ids:
                attempt_conditions.append(TTSJobAttempt.job_id.in_(job_ids))
            if worker_ids:
                attempt_conditions.append(TTSJobAttempt.worker_id.in_(worker_ids))
            if attempt_conditions:
                delete_plan.extend(
                    [
                        ("tts_job_attempts", TTSJobAttempt, or_(*attempt_conditions)),
                        ("tts_jobs", TTSJob, or_(*job_conditions)),
                    ]
                )
            delete_plan.append(("workers", Worker, Worker.owner_user_id == user_id))

        if channel_names:
            delete_plan.extend(
                [
                    (
                        "whitelisted_channels",
                        WhitelistedChannel,
                        func.lower(WhitelistedChannel.channel_name).in_(channel_names),
                    ),
                    (
                        "blocked_channels",
                        BlockedChannel,
                        func.lower(BlockedChannel.channel_name).in_(channel_names),
                    ),
                    (
                        "achievements",
                        Achievement,
                        func.lower(Achievement.channel_name).in_(channel_names),
                    ),
                ]
            )

        admin_conditions = [AdminUser.created_by == user_id]
        if platform_user_ids:
            admin_conditions.append(AdminUser.platform_user_id.in_(platform_user_ids))
        delete_plan.append(("admin_users", AdminUser, or_(*admin_conditions)))

        counts = {
            table_name: self._count_rows(db, model, condition)
            for table_name, model, condition in delete_plan
        }
        counts["users"] = 1

        preview = UserDeletionPreview(
            user_id=user_id,
            username=user.twitch_username or user.vk_username or f"user_{user_id}",
            role=user.role,
            channel_names=channel_names,
            platform_user_ids=platform_user_ids,
            counts=counts,
            total_rows=sum(counts.values()),
        )
        return preview, delete_plan

    def _count_rows(self, db: Session, model: object, condition: object) -> int:
        return int(
            db.execute(select(func.count()).select_from(model).where(condition)).scalar_one()
        )


user_cleanup_service = UserCleanupService()
