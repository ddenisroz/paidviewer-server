import logging
from datetime import timedelta
from typing import List, Optional, Tuple

import aiohttp
from sqlalchemy.orm import Session

from core.config import settings
from core.database import ChatMessage
from core.datetime_utils import utcnow_naive
from repositories.chat_message_repository import ChatMessageRepository
from repositories.psychology_repository import PsychologyRepository
from repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


class PsychologyService:
    """Analyze chat messages to build a lightweight personality profile."""

    _analysis_in_progress = False
    _last_analysis_time: dict = {}

    def __init__(self, db: Session):
        self.db = db

    async def analyze_user_psychology(
        self,
        target_username: str,
        platform: str,
        analyzed_by_user_id: int,
        analyzed_by_username: str,
        channel_name: str,
    ) -> Optional[str]:
        """
        Analyze a user's chat style and produce a short personality profile.

        Args:
            target_username: Username to analyze.
            platform: Source platform (twitch/vk).
            analyzed_by_user_id: ID of the requesting user.
            analyzed_by_username: Username of the requesting user.
            channel_name: Channel where the request was initiated.

        Returns:
            Analysis result string or ``None`` on failure.
        """
        try:
            current_time = utcnow_naive()
            if analyzed_by_user_id in self.__class__._last_analysis_time:
                time_diff = current_time - self.__class__._last_analysis_time[analyzed_by_user_id]
                if time_diff.total_seconds() < 30:
                    remaining = 30 - int(time_diff.total_seconds())
                    return f"[TIMEOUT] Please wait {remaining} seconds before running another analysis"

            if self.__class__._analysis_in_progress:
                return "[REFRESH] Analysis is already running, please wait..."

            if not self._check_database_health():
                return "[WARN] Database load is too high, analysis is temporarily unavailable"

            self.__class__._analysis_in_progress = True
            self.__class__._last_analysis_time[analyzed_by_user_id] = current_time
            target_username = (target_username or "").strip().lstrip("@")
            if not target_username:
                self.__class__._analysis_in_progress = False
                return "[ERROR] Please specify a user to analyze"

            channel_limit = settings.chat_analysis_channel_limit
            global_limit = settings.chat_analysis_global_limit
            min_messages = settings.chat_analysis_min_messages
            channel_messages, global_messages = self._get_user_messages(
                owner_user_id=analyzed_by_user_id,
                username=target_username,
                platform=platform,
                channel_name=channel_name,
                channel_limit=channel_limit,
                global_limit=global_limit,
            )
            if not global_messages:
                self.__class__._analysis_in_progress = False
                return f"[ERROR] No messages found for user {target_username}"

            channel_text, channel_count = self._prepare_messages_for_analysis(channel_messages)
            global_text, global_count = self._prepare_messages_for_analysis(global_messages)
            if global_count < min_messages:
                self.__class__._analysis_in_progress = False
                return (
                    f"[ERROR] Not enough messages for analysis "
                    f"(found: {global_count}, minimum: {min_messages})"
                )
            if not channel_text and not global_text:
                self.__class__._analysis_in_progress = False
                return "[ERROR] Failed to prepare messages for analysis"

            analysis_result = await self._request_ai_analysis(
                target_username=target_username,
                platform=platform,
                channel_name=channel_name,
                channel_text=channel_text,
                channel_count=channel_count,
                global_text=global_text,
                global_count=global_count,
            )
            if analysis_result:
                if analysis_result.startswith("[ERROR]"):
                    self.__class__._analysis_in_progress = False
                    return analysis_result
                if settings.chat_analysis_save_results:
                    self._save_analysis_result(
                        target_username,
                        platform,
                        analyzed_by_user_id,
                        analyzed_by_username,
                        analysis_result,
                        global_count,
                    )
                    logger.info("Psychology analysis saved for %s", target_username)
                else:
                    logger.info("Psychology analysis completed for %s (not saved to DB)", target_username)
                self.__class__._analysis_in_progress = False
                return analysis_result

            self.__class__._analysis_in_progress = False
            return "[ERROR] Analysis failed. Please try again later."
        except Exception:
            logger.exception("Error in analyze_user_psychology")
            self.__class__._analysis_in_progress = False
            return "[ERROR] An error occurred during analysis"

    def _get_user_messages(
        self,
        owner_user_id: int,
        username: str,
        platform: str,
        channel_name: str,
        channel_limit: int,
        global_limit: int,
    ) -> Tuple[List[ChatMessage], List[ChatMessage]]:
        """Return channel-scoped and global messages for the target user."""
        try:
            repo = ChatMessageRepository(self.db)
            channel_messages = repo.get_recent_by_author_in_channel(
                user_id=owner_user_id,
                author_username=username,
                channel_name=channel_name,
                platform=platform,
                limit=channel_limit,
            )
            global_messages = repo.get_recent_by_author(
                user_id=owner_user_id,
                author_username=username,
                platform=platform,
                limit=global_limit,
            )
            return channel_messages, global_messages
        except Exception:
            logger.exception("Error getting user messages")
            return [], []

    def _check_database_health(self) -> bool:
        """Check whether database load is healthy enough for analysis."""
        try:
            from services.database_cleanup_service import DatabaseCleanupService

            cleanup_service = DatabaseCleanupService(self.db)
            stats = cleanup_service.get_database_stats()
            total_messages = stats.get("total_chat_messages", 0)
            max_total_messages = stats.get("max_total_messages", 100000)
            users_over_limit = stats.get("users_over_message_limit", 0)
            if total_messages > max_total_messages * 0.9:
                logger.warning(
                    "Database approaching total limit: %s/%s messages",
                    total_messages,
                    max_total_messages,
                )
                return False
            if users_over_limit > 0:
                logger.warning("Users over message limit: %s", users_over_limit)
                return False
            return True
        except Exception:
            logger.exception("Error checking database health")
            return True

    def _prepare_messages_for_analysis(self, messages: List[ChatMessage], max_chars: int = 2000) -> Tuple[str, int]:
        """Prepare messages for the AI request."""
        try:
            message_texts = []
            for msg in messages:
                text = (msg.message or "").strip()
                if not text or text.startswith("!"):
                    continue
                text = " ".join(text.split())
                if len(text) > 200:
                    text = text[:200] + "..."
                message_texts.append(text)
            combined_text = " | ".join(message_texts)
            if len(combined_text) > max_chars:
                combined_text = combined_text[:max_chars] + "..."
            return combined_text, len(message_texts)
        except Exception:
            logger.exception("Error preparing messages")
            return "", 0

    async def _call_deepseek(self, system_prompt: str, user_prompt: str, max_tokens: int) -> Optional[str]:
        """Send a request to DeepSeek chat completions."""
        if not settings.deepseek_api_key:
            return None
        url = f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.deepseek_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
            "max_tokens": max_tokens,
            "stream": False,
        }
        timeout = aiohttp.ClientTimeout(total=25)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error("DeepSeek API error: %s - %s", response.status, error_text)
                    return None
                data = await response.json()
        try:
            return (data.get("choices") or [{}])[0].get("message", {}).get("content")
        except Exception:
            return None

    def _normalize_analysis_output(self, text: str) -> str:
        """Normalize analysis output."""
        if not text:
            return ""
        return " ".join(text.split())

    def _has_required_labels(self, text: str) -> bool:
        """Validate the expected analysis label format."""
        lower = text.lower()
        required = ["aggression", "dimpling", "sense of humor", "attention-seeking"]
        return all(label in lower for label in required)

    async def _request_ai_analysis(
        self,
        target_username: str,
        platform: str,
        channel_name: str,
        channel_text: str,
        channel_count: int,
        global_text: str,
        global_count: int,
    ) -> Optional[str]:
        """Request a personality summary from the AI provider."""
        try:
            if not settings.deepseek_api_key:
                return "[ERROR] DeepSeek API key is not configured"

            system_prompt = (
                "Analyze the user's communication style based on chat messages. "
                "Return a short personality portrait without medical diagnosis, insults, or harassment. "
                "The answer must be a single line, 100-150 characters long. "
                "Start with a very short portrait (20-40 characters), then provide ratings. "
                "The final line must include these labels: aggression, dimpling, sense of humor, attention-seeking. "
                "Use this exact rating format: 'aggression 3/10, dimpling 2/10, sense of humor 7/10, attention-seeking 4/10'. "
                "Do not add anything else."
            )
            user_prompt = (
                f"User: {target_username}\n"
                f"Platform: {platform}\n"
                f"Channel: {channel_name} (messages: {channel_count})\n"
                f"CHANNEL_MESSAGES: {channel_text or 'none'}\n"
                f"GLOBAL_MESSAGES (all channels, messages: {global_count}): {global_text or 'none'}\n"
                "CHANNEL_MESSAGES are more important, but consider both blocks."
            )
            max_chars = settings.chat_analysis_output_max_chars
            analysis = await self._call_deepseek(system_prompt, user_prompt, max_tokens=120)
            analysis = self._normalize_analysis_output(analysis or "")
            if analysis and (len(analysis) > max_chars or not self._has_required_labels(analysis)):
                short_prompt = system_prompt + " The answer must be even shorter and strictly follow the format."
                analysis = await self._call_deepseek(short_prompt, user_prompt, max_tokens=80)
                analysis = self._normalize_analysis_output(analysis or "")
            if analysis and len(analysis) > max_chars:
                analysis = analysis[:max_chars].rstrip()
            return analysis or None
        except Exception:
            logger.exception("Error requesting AI analysis")
            return None

    def _save_analysis_result(
        self,
        target_username: str,
        platform: str,
        analyzed_by_user_id: int,
        analyzed_by_username: str,
        analysis_text: str,
        messages_count: int,
    ):
        """Persist the completed analysis result."""
        try:
            user_repo = UserRepository(self.db)
            if platform == "vk":
                target_user = user_repo.get_by_vk_username(target_username)
            else:
                target_user = user_repo.get_by_twitch_username(target_username)
            if not target_user:
                logger.error("Target user %s not found for platform %s", target_username, platform)
                return
            repo = PsychologyRepository(self.db)
            repo.add_analysis(
                target_user_id=target_user.id,
                target_username=target_username,
                platform=platform,
                analyzed_by_user_id=analyzed_by_user_id,
                analyzed_by_username=analyzed_by_username,
                analysis_text=analysis_text,
                messages_count=messages_count,
            )
            logger.info("Psychology analysis saved for %s", target_username)
        except Exception:
            logger.exception("Error saving analysis result")

    def get_recent_analysis(self, target_username: str, platform: str, hours: int = 24) -> Optional[str]:
        """Return a recent analysis for the user if one exists."""
        try:
            cutoff_time = utcnow_naive() - timedelta(hours=hours)
            repo = PsychologyRepository(self.db)
            analysis = repo.get_recent_analysis(target_username, platform, cutoff_time)
            if analysis:
                return analysis.analysis_text
            return None
        except Exception:
            logger.exception("Error getting recent analysis")
            return None
