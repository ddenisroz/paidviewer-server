"""Background reconciler for worker control-plane state."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from sqlalchemy import inspect

from core.config import settings
from core.database import get_db
from services.worker_control.service import WorkerControlPlaneService


logger = logging.getLogger(__name__)


class WorkerControlReconciler:
    """Periodically reconciles stale workers and expired job leases."""

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._schema_warning_logged = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Worker control reconciler started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Worker control reconciler stopped")

    async def _loop(self) -> None:
        interval = max(1, int(settings.worker_reconcile_interval_seconds))
        while self._running:
            try:
                await self._run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Worker control reconciliation failed")
            await asyncio.sleep(interval)

    async def _run_once(self) -> None:
        db = next(get_db())
        try:
            inspector = inspect(db.get_bind())
            required_tables = ("workers", "worker_pairing_tokens", "tts_jobs", "tts_job_attempts")
            missing_tables = [table_name for table_name in required_tables if not inspector.has_table(table_name)]
            if missing_tables:
                if not self._schema_warning_logged:
                    logger.warning(
                        "Worker control reconciler is waiting for schema migration; missing tables: %s",
                        ", ".join(missing_tables),
                    )
                    self._schema_warning_logged = True
                return
            self._schema_warning_logged = False
            result = WorkerControlPlaneService(db).reconcile_workers_and_jobs()
            if result.get("requeued_jobs"):
                logger.info(
                    "Worker control reconciliation requeued %s expired jobs",
                    result["requeued_jobs"],
                )
        finally:
            db.close()


worker_control_reconciler = WorkerControlReconciler()
