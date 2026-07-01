# bot_service/services/tts/tts_worker.py
"""
TTS Worker processes tasks from MemoryTTSQueue.
It decouples the API (producer) from the synthesis logic (consumer).
"""
import asyncio
import logging
import traceback
from typing import Optional

from repositories.blocked_user_repository import BlockedUserRepository
from repositories.filtered_word_repository import FilteredWordRepository
from services.tts.memory_tts_queue import get_memory_tts_queue, TTSTask, TaskStatus
from services.tts.tts_manager import get_tts_manager
from core.database import SessionLocal
from core.connection_manager import get_connection_manager
from services.notification_service import notification_service

logger = logging.getLogger(__name__)

class TTSWorker:
    """
    Background worker that consumes tasks from MemoryTTSQueue
    and executes synthesis via TTSManager.
    """
    
    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self.tts_manager = get_tts_manager()
        self.connection_manager = get_connection_manager()

    async def start(self):
        """Start the worker loop."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._worker_loop())
        logger.info("TTS Worker started")

    async def stop(self):
        """Stop the worker loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("TTS Worker stopped")

    async def _worker_loop(self):
        """Main processing loop."""
        logger.info("TTS Worker loop running...")
        
        while self._running:
            try:
                # 1. Get next task (with timeout to allow checking _running)
                task = await get_memory_tts_queue().get_next_task(timeout=1.0)
                
                if not task:
                    continue

                # 2. Process task
                await self._process_task(task)

            except Exception as e:
                logger.exception("Error in TTS Worker loop")
                await asyncio.sleep(1.0) # Prevent tight loop on error

    async def _process_task(self, task: TTSTask):
        """Execute a single TTS task."""
        try:
            logger.info(f"Processing TTS task {task.task_id} for user {task.user_id}")

            db = SessionLocal()
            try:
                volume = getattr(task, 'meta_volume', 50.0)
                author = getattr(task, 'meta_author', 'System')
                use_ai = getattr(task, 'meta_use_ai', True)
                tts_settings = getattr(task, 'meta_settings', None)
                engine = None
                if isinstance(tts_settings, dict):
                    engine = str(tts_settings.get("engine") or "").strip() or None
                word_filter = getattr(task, 'meta_word_filter', None)
                blocked_users = getattr(task, 'meta_blocked_users', None)
                if word_filter is None:
                    word_filter = [
                        str(item.word).strip().lower()
                        for item in FilteredWordRepository(db).get_by_user_id(task.user_id)
                        if getattr(item, "word", None)
                    ]
                if blocked_users is None:
                    blocked_users = [
                        str(item.username).strip().lower()
                        for item in BlockedUserRepository(db).get_by_user_id(task.user_id)
                        if getattr(item, "username", None)
                    ]
                
                result = await self.tts_manager.synthesize_tts(
                    channel_name=task.channel,
                    text=task.text,
                    author=author,
                    user_id=task.user_id,
                    volume_level=volume,
                    use_ai_tts=use_ai,
                    use_basic_tts=not use_ai,
                    connection_manager=self.connection_manager,
                    db_session=db,
                    tts_settings=tts_settings,
                    word_filter=word_filter,
                    blocked_users=blocked_users,
                    engine=engine,
                )
                
                if result.get("success"):
                    await get_memory_tts_queue().complete_task(task.task_id, result)
                    await self._broadcast_completed_task(task, result)
                else:
                    await get_memory_tts_queue().fail_task(task.task_id, result.get("error", "Unknown error"))
                    
            finally:
                db.close()
                
        except Exception as e:
            logger.exception("Failed to process task %s", task.task_id)
            logger.error(traceback.format_exc())
            await get_memory_tts_queue().fail_task(task.task_id, str(e))

    async def _broadcast_completed_task(self, task: TTSTask, result: dict) -> None:
        """Deliver synthesized queued audio to the active TTS sink."""
        metadata = task.metadata or {}
        source_message_id = (
            metadata.get("source_message_id")
            or getattr(task, "meta_source_message_id", None)
        )
        trace_id = metadata.get("trace_id") or getattr(task, "meta_trace_id", None)
        try:
            await notification_service.broadcast_tts_audio(
                audio_data={
                    "audio_url": result.get("audio_url"),
                    "voice": result.get("voice", task.voice or "unknown"),
                    "volume": result.get("volume", getattr(task, "meta_volume", 50.0)),
                    "tts_type": result.get("tts_type", "unknown"),
                    "duration": result.get("duration", 0),
                    "text": task.text,
                    "spoken_text": result.get("spoken_text") or task.text,
                    "original_text": metadata.get("original_text") or task.text,
                    "username": getattr(task, "meta_author", None) or metadata.get("author") or "System",
                    "trace_id": trace_id,
                    "source_message_id": source_message_id,
                    "requested_provider": result.get("requested_provider"),
                    "actual_provider": result.get("actual_provider"),
                    "fallback_used": bool(result.get("fallback_used")),
                    "fallback_reason": result.get("fallback_reason"),
                },
                channel_name=task.channel,
                platform=task.platform,
            )
        except Exception:
            logger.exception("Failed to broadcast completed TTS task %s", task.task_id)

# Global instance
tts_worker = TTSWorker()

