"""Repository helpers for PostgreSQL-backed worker jobs."""

from __future__ import annotations

from datetime import timedelta
from typing import Iterable, Optional

from sqlalchemy import and_, false, or_
from sqlalchemy.orm import Session

from core.datetime_utils import utcnow_naive
from models.worker import TTSJob, TTSJobAttempt, Worker


class TTSJobRepository:
    """Database operations for worker jobs and attempt tracking."""

    def __init__(self, db: Session):
        self.db = db

    def create_job(self, job: TTSJob) -> TTSJob:
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get_job(self, job_id: str) -> Optional[TTSJob]:
        return self.db.query(TTSJob).filter(TTSJob.id == job_id).first()

    def get_job_for_user(self, job_id: str, owner_user_id: int) -> Optional[TTSJob]:
        return (
            self.db.query(TTSJob)
            .filter(TTSJob.id == job_id, TTSJob.owner_user_id == owner_user_id)
            .first()
        )

    def create_attempt(self, attempt: TTSJobAttempt) -> TTSJobAttempt:
        self.db.add(attempt)
        self.db.flush()
        return attempt

    def get_open_attempt(self, job_id: str, attempt_number: int) -> Optional[TTSJobAttempt]:
        return (
            self.db.query(TTSJobAttempt)
            .filter(
                TTSJobAttempt.job_id == job_id,
                TTSJobAttempt.attempt_number == attempt_number,
                TTSJobAttempt.finished_at.is_(None),
            )
            .first()
        )

    @staticmethod
    def _resolve_job_max_attempts(job: TTSJob, fallback_max_attempts: int = 3) -> int:
        return max(1, int(job.max_attempts or fallback_max_attempts or 1))

    def requeue_expired_jobs(self, *, now=None, max_attempts: int = 3) -> int:
        now = now or utcnow_naive()
        stale_jobs = (
            self.db.query(TTSJob)
            .filter(
                TTSJob.status == "leased",
                TTSJob.lease_expires_at.is_not(None),
                TTSJob.lease_expires_at < now,
            )
            .all()
        )
        if not stale_jobs:
            return 0

        requeued = 0
        for job in stale_jobs:
            attempt = self.get_open_attempt(job.id, job.attempt_count)
            if attempt:
                attempt.status = "lease_expired"
                attempt.error_code = "lease_expired"
                attempt.error_message = "Worker lease expired before completion"
                attempt.finished_at = now

            resolved_max_attempts = self._resolve_job_max_attempts(job, max_attempts)
            if job.attempt_count >= resolved_max_attempts:
                job.status = "failed"
                job.completed_at = now
                job.lease_expires_at = None
                job.error_code = "lease_expired"
                job.error_message = "Job exceeded max attempts after repeated lease expiry"
            else:
                job.status = "queued"
                job.assigned_worker_id = None
                job.lease_expires_at = None
                job.completed_at = None
                job.error_code = "lease_expired"
                job.error_message = "Previous worker lease expired; job requeued"
                job.scheduled_at = now
                requeued += 1

        self.db.commit()
        return requeued

    def _provider_filter(self, worker: Worker):
        if not worker.supports_f5:
            return false()
        return TTSJob.provider == "f5"

    def _ownership_filter(self, worker: Worker):
        owned_filter = and_(
            TTSJob.target_worker_id.is_(None),
            TTSJob.owner_user_id.is_not(None),
            TTSJob.owner_user_id == worker.owner_user_id,
        )
        targeted_filter = TTSJob.target_worker_id == worker.id

        if worker.is_managed:
            managed_filter = and_(
                TTSJob.target_worker_id.is_(None),
                TTSJob.owner_user_id.is_(None),
            )
            return or_(targeted_filter, managed_filter, owned_filter)
        return or_(targeted_filter, owned_filter)

    def claim_jobs(
        self,
        *,
        worker: Worker,
        max_jobs: int,
        lease_seconds: int,
        max_attempts: int,
    ) -> list[TTSJob]:
        now = utcnow_naive()
        query = (
            self.db.query(TTSJob)
            .filter(
                TTSJob.status == "queued",
                TTSJob.scheduled_at <= now,
                TTSJob.attempt_count < TTSJob.max_attempts,
                self._provider_filter(worker),
                self._ownership_filter(worker),
            )
            .order_by(TTSJob.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(max_jobs)
        )
        jobs = list(query.all())
        if not jobs:
            return []

        lease_expires_at = now + timedelta(seconds=lease_seconds)
        claimed_jobs: list[TTSJob] = []
        for job in jobs:
            job.status = "leased"
            job.assigned_worker_id = worker.id
            job.lease_expires_at = lease_expires_at
            job.started_at = job.started_at or now
            job.attempt_count = int(job.attempt_count or 0) + 1
            self.create_attempt(
                TTSJobAttempt(
                    job_id=job.id,
                    worker_id=worker.id,
                    provider=job.provider,
                    status="leased",
                    attempt_number=job.attempt_count,
                )
            )
            resolved_max_attempts = self._resolve_job_max_attempts(job, max_attempts)
            if job.attempt_count > resolved_max_attempts:
                attempt = self.get_open_attempt(job.id, job.attempt_count)
                if attempt:
                    attempt.status = "max_attempts_exceeded"
                    attempt.error_code = "max_attempts_exceeded"
                    attempt.error_message = "Job was claimed after exceeding max attempts"
                    attempt.finished_at = now
                job.status = "failed"
                job.completed_at = now
                job.lease_expires_at = None
                job.error_code = "max_attempts_exceeded"
                job.error_message = "Job was claimed after exceeding max attempts"
                continue
            claimed_jobs.append(job)

        self.db.commit()
        return claimed_jobs

    def complete_job(
        self,
        *,
        job: TTSJob,
        worker: Worker,
        result_audio_url: Optional[str],
        result_payload: dict,
    ) -> TTSJob:
        now = utcnow_naive()
        job.status = "completed"
        job.assigned_worker_id = worker.id
        job.lease_expires_at = None
        job.completed_at = now
        job.result_audio_url = result_audio_url
        job.result_payload = result_payload or {}
        job.error_code = None
        job.error_message = None

        attempt = self.get_open_attempt(job.id, job.attempt_count)
        if attempt:
            attempt.status = "completed"
            attempt.result_audio_url = result_audio_url
            attempt.finished_at = now

        self.db.commit()
        self.db.refresh(job)
        return job

    def fail_job(
        self,
        *,
        job: TTSJob,
        worker: Worker,
        error_code: str,
        error_message: str,
        retryable: bool,
        max_attempts: int,
    ) -> TTSJob:
        now = utcnow_naive()
        attempt = self.get_open_attempt(job.id, job.attempt_count)
        if attempt:
            attempt.status = "failed"
            attempt.error_code = error_code
            attempt.error_message = error_message
            attempt.finished_at = now

        resolved_max_attempts = self._resolve_job_max_attempts(job, max_attempts)
        if retryable and job.attempt_count < resolved_max_attempts:
            backoff_seconds = min(30 * max(1, job.attempt_count), 300)
            job.status = "queued"
            job.assigned_worker_id = None
            job.lease_expires_at = None
            job.completed_at = None
            job.scheduled_at = now + timedelta(seconds=backoff_seconds)
        else:
            job.status = "failed"
            job.completed_at = now
            job.lease_expires_at = None
            job.assigned_worker_id = worker.id

        job.error_code = error_code
        job.error_message = error_message
        self.db.commit()
        self.db.refresh(job)
        return job

    def release_jobs_for_worker(
        self,
        worker_id: int,
        *,
        error_code: str = "worker_unavailable",
        error_message: str = "Target worker became unavailable",
    ) -> int:
        now = utcnow_naive()
        jobs: Iterable[TTSJob] = (
            self.db.query(TTSJob)
            .filter(
                or_(TTSJob.target_worker_id == worker_id, TTSJob.assigned_worker_id == worker_id),
                TTSJob.status.in_(("queued", "leased")),
            )
            .all()
        )
        released = 0
        for job in jobs:
            attempt = self.get_open_attempt(job.id, job.attempt_count)
            if attempt:
                attempt.status = "worker_unavailable"
                attempt.error_code = error_code
                attempt.error_message = error_message
                attempt.finished_at = now

            max_attempts = max(1, int(job.max_attempts or 1))
            if int(job.attempt_count or 0) >= max_attempts:
                job.status = "failed"
                job.completed_at = now
            else:
                job.status = "queued"
                job.completed_at = None
                job.scheduled_at = now
                released += 1
            job.target_worker_id = None
            job.assigned_worker_id = None
            job.lease_expires_at = None
            job.error_code = error_code
            job.error_message = error_message
        self.db.commit()
        return released
