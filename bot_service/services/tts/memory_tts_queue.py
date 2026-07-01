# bot_service/services/memory_tts_queue.py
"""In-memory TTS task queue."""
import asyncio
import logging
import time
import uuid
from typing import Dict, Any, Optional, Set
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class TTSTask:
    """TTS synthesis task."""
    task_id: str
    user_id: int
    text: str
    voice: str
    channel: str
    platform: str
    priority: int
    status: TaskStatus
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class MemoryTTSQueue:
    """
    In-memory TTS task queue.

    The queue tracks users with disabled generation and verifies active sinks
    before enqueuing new work.
    """

    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.tasks: Dict[str, TTSTask] = {}
        self.pending_queue = asyncio.Queue(maxsize=max_size)
        self.completed_tasks: Dict[str, TTSTask] = {}
        self._running = False
        self._cleanup_task: Optional[asyncio.Task] = None
        self._cleanup_interval_seconds = 600
        self.max_completed_tasks = 5000
        # Track users for whom TTS generation is currently disabled.
        self.disabled_users: Set[int] = set()

    def _mark_task_dropped(self, task: TTSTask, reason: str):
        """Mark queued task as dropped without processing."""
        task.status = TaskStatus.FAILED
        task.completed_at = time.time()
        task.error = reason
        self.completed_tasks[task.task_id] = task
        self.tasks.pop(task.task_id, None)
        self._trim_completed_tasks()

    def _trim_completed_tasks(self):
        """Cap completed task storage to prevent unbounded growth."""
        overflow = len(self.completed_tasks) - self.max_completed_tasks
        if overflow <= 0:
            return

        oldest_task_ids = sorted(
            self.completed_tasks.keys(),
            key=lambda task_id: self.completed_tasks[task_id].completed_at or 0.0,
        )[:overflow]
        for task_id in oldest_task_ids:
            self.completed_tasks.pop(task_id, None)

    async def _cleanup_loop(self):
        """Periodic cleanup for terminal tasks."""
        while self._running:
            try:
                await asyncio.sleep(self._cleanup_interval_seconds)
                await self.cleanup_old_tasks(max_age_hours=24)
                self._trim_completed_tasks()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Error in memory TTS queue cleanup loop")

    async def start(self):
        """Start the queue."""
        if self._running:
            return

        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Memory TTS Queue started")

    async def stop(self):
        """Stop the queue."""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
        logger.info("Memory TTS Queue stopped")

    async def add_task(
        self,
        user_id: int,
        text: str,
        voice: str,
        channel: str = None,
        platform: str = "twitch",
        priority: int = 2,
        metadata: Dict[str, Any] = None
    ) -> str:
        """
        Add a task to the queue.

        Active sink validation is performed before the task is accepted.

        Args:
            user_id: User ID.
            text: Text for synthesis.
            voice: Voice identifier.
            channel: Channel name.
            platform: Source platform.
            priority: Task priority (1-4).
            metadata: Optional metadata.

        Returns:
            Task ID.

        Raises:
            RuntimeError: If the queue is not running, full, or the user has no active sink.
        """
        if not self._running:
            raise RuntimeError("Queue is not running")

        if self.pending_queue.qsize() >= self.max_size:
            raise RuntimeError("Queue is full")

        # Skip users whose generation is currently disabled.
        if user_id in self.disabled_users:
            logger.info(f"Skipping TTS for user {user_id} - TTS generation disabled")
            raise RuntimeError(f"TTS generation disabled for user {user_id}")

        # Require an active sink before enqueueing new work.
        if not self.is_user_connected(user_id):
            logger.info(f"Skipping TTS for user {user_id} - no active connections")
            raise RuntimeError(f"User {user_id} has no active connections")

        task_id = str(uuid.uuid4())

        if not channel:
            channel = f"user_{user_id}"

        task = TTSTask(
            task_id=task_id,
            user_id=user_id,
            text=text,
            voice=voice,
            channel=channel,
            platform=platform,
            priority=priority,
            status=TaskStatus.PENDING,
            created_at=time.time(),
            metadata=dict(metadata or {}),
        )

        # Attach metadata to the task if present.
        if metadata:
            for key, value in metadata.items():
                setattr(task, f"meta_{key}", value)

        self.tasks[task_id] = task

        # Queue the task.
        await self.pending_queue.put(task)

        logger.info(f"TTS task added: {task_id} for user {user_id}")
        return task_id

    async def get_next_task(self, timeout: float = 1.0) -> Optional[TTSTask]:
        """
        Get the next task from the queue.

        Args:
            timeout: Wait timeout in seconds.

        Returns:
            ``TTSTask`` or ``None`` if the queue is empty.
        """
        if not self._running:
            return None

        try:
            while self._running:
                task = await asyncio.wait_for(
                    self.pending_queue.get(),
                    timeout=timeout
                )

                if task.user_id in self.disabled_users:
                    self._mark_task_dropped(task, "TTS generation disabled for user")
                    logger.info(f"Dropped TTS task {task.task_id}: user {task.user_id} is disabled")
                    continue

                if not self.is_user_connected(task.user_id):
                    self._mark_task_dropped(task, "No active TTS listeners")
                    logger.info(f"Dropped TTS task {task.task_id}: user {task.user_id} has no listeners")
                    continue

                # Update runtime status before handing the task to a worker.
                task.status = TaskStatus.PROCESSING
                task.started_at = time.time()

                logger.info(f"TTS task started: {task.task_id}")
                return task

            return None

        except asyncio.TimeoutError:
            return None
        except Exception:
            logger.exception("Error getting next task")
            return None

    async def complete_task(self, task_id: str, result: Dict[str, Any]):
        """
        Mark a task as completed.

        Args:
            task_id: Task ID.
            result: Task result payload.
        """
        if task_id not in self.tasks:
            logger.warning(f"Task not found: {task_id}")
            return

        task = self.tasks[task_id]
        task.status = TaskStatus.COMPLETED
        task.completed_at = time.time()
        task.result = result

        # Move the task into terminal storage.
        self.completed_tasks[task_id] = task
        self.tasks.pop(task_id, None)
        self._trim_completed_tasks()

        logger.info(f"TTS task completed: {task_id}")

    async def fail_task(self, task_id: str, error: str):
        """
        Mark a task as failed.

        Args:
            task_id: Task ID.
            error: Error message.
        """
        if task_id not in self.tasks:
            logger.warning(f"Task not found: {task_id}")
            return

        task = self.tasks[task_id]
        task.status = TaskStatus.FAILED
        task.completed_at = time.time()
        task.error = error

        # Move the task into terminal storage.
        self.completed_tasks[task_id] = task
        self.tasks.pop(task_id, None)
        self._trim_completed_tasks()

        logger.error("TTS task failed: %s - %s", task_id, error)

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get task status.

        Args:
            task_id: Task ID.

        Returns:
            A task info dictionary or ``None``.
        """
        if task_id in self.tasks:
            task = self.tasks[task_id]
        elif task_id in self.completed_tasks:
            task = self.completed_tasks[task_id]
        else:
            return None

        return {
            "task_id": task.task_id,
            "user_id": task.user_id,
            "status": task.status.value,
            "created_at": task.created_at,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "result": task.result,
            "error": task.error
        }

    def get_queue_stats(self) -> Dict[str, Any]:
        """
        Get queue statistics.

        Returns:
            Queue statistics dictionary.
        """
        pending_count = self.pending_queue.qsize()
        processing_count = sum(1 for task in self.tasks.values()
                             if task.status == TaskStatus.PROCESSING)
        completed_count = len(self.completed_tasks)
        failed_count = sum(1 for task in self.completed_tasks.values()
                          if task.status == TaskStatus.FAILED)

        return {
            "queue_name": "memory_tts_queue",
            "pending_tasks": pending_count,
            "processing_tasks": processing_count,
            "completed_tasks": completed_count,
            "failed_tasks": failed_count,
            "total_tasks": len(self.tasks) + len(self.completed_tasks),
            "max_size": self.max_size,
            "running": self._running
        }

    async def cleanup_old_tasks(self, max_age_hours: int = 24):
        """
        Remove old completed tasks.

        Args:
            max_age_hours: Maximum completed-task age in hours.
        """
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600

        # Drop terminal tasks older than the configured threshold.
        old_tasks = []
        for task_id, task in list(self.completed_tasks.items()):
            if task.completed_at and (current_time - task.completed_at) > max_age_seconds:
                old_tasks.append(task_id)

        for task_id in old_tasks:
            del self.completed_tasks[task_id]
            if task_id in self.tasks:
                del self.tasks[task_id]

        if old_tasks:
            logger.info(f"Cleaned up {len(old_tasks)} old tasks")

    def is_user_connected(self, user_id: int) -> bool:
        """
        Check whether the user still has active connections.

        Args:
            user_id: User ID.

        Returns:
            ``True`` if the user has an active connection.
        """
        try:
            from services.memory_websocket_manager import get_memory_websocket_manager

            # Check active user connections through the in-memory WebSocket manager.
            conn_mgr = get_memory_websocket_manager()
            return user_id in conn_mgr.user_connections and \
                   len(conn_mgr.user_connections[user_id]) > 0
        except Exception:
            logger.exception("Error checking user connection")
            # Fail-closed: if sink state cannot be verified, do not enqueue TTS.
            return False

    async def disable_for_user(self, user_id: int):
        """
        Disable TTS generation for a user.

        Called when the user fully disconnects and no sinks remain.

        Args:
            user_id: User ID.
        """
        self.disabled_users.add(user_id)
        removed_tasks = 0
        kept_tasks = []

        while True:
            try:
                task = self.pending_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            if task.user_id == user_id:
                self._mark_task_dropped(task, "TTS generation disabled (no active listeners)")
                removed_tasks += 1
            else:
                kept_tasks.append(task)

        for task in kept_tasks:
            self.pending_queue.put_nowait(task)

        logger.info(f"Disabled TTS generation for user {user_id}. Dropped pending tasks: {removed_tasks}")

    async def enable_for_user(self, user_id: int):
        """
        Re-enable TTS generation for a user.

        Called when the user reconnects.

        Args:
            user_id: User ID.
        """
        self.disabled_users.discard(user_id)
        logger.info(f"Enabled TTS generation for user {user_id}")

# Global singleton instance.
_memory_tts_queue: Optional[MemoryTTSQueue] = None

def get_memory_tts_queue() -> MemoryTTSQueue:
    """
    Get or create the global MemoryTTSQueue instance.
    """
    global _memory_tts_queue
    if _memory_tts_queue is None:
        _memory_tts_queue = MemoryTTSQueue()
    return _memory_tts_queue



