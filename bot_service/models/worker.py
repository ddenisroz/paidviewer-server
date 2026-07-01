"""Worker control-plane models for self-hosted and managed TTS agents."""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.sqlite import JSON as SQLITE_JSON
from sqlalchemy.types import JSON

from core.datetime_utils import utcnow_naive
from models.base import Base


JsonType = JSON().with_variant(SQLITE_JSON, "sqlite")


class Worker(Base):
    """Registered worker-agent instance."""

    __tablename__ = "workers"
    __table_args__ = (
        Index("ix_workers_owner_active", "owner_user_id", "is_active"),
        Index("ix_workers_status_active", "status", "is_active"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    worker_key = Column(String, nullable=False, unique=True, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    label = Column(String, nullable=False, default="TTS Worker")
    auth_token_hash = Column(String, nullable=False, unique=True, index=True)
    supports_f5 = Column(Boolean, nullable=False, default=False, index=True)
    capabilities = Column(JsonType, nullable=False, default=dict)
    runtime_metadata = Column(JsonType, nullable=False, default=dict)
    status = Column(String, nullable=False, default="offline", index=True)
    last_seen_at = Column(DateTime, nullable=True, index=True)
    last_error = Column(String, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    is_managed = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime, default=utcnow_naive, nullable=False)
    updated_at = Column(DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=False)


class WorkerPairingToken(Base):
    """One-time pairing token issued to an authenticated user."""

    __tablename__ = "worker_pairing_tokens"
    __table_args__ = (
        Index("ix_worker_pairing_tokens_owner_expires", "owner_user_id", "expires_at"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    token_hash = Column(String, nullable=False, unique=True, index=True)
    label_hint = Column(String, nullable=True)
    provider_hint = Column(String, nullable=True)
    is_managed = Column(Boolean, nullable=False, default=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    used_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=utcnow_naive, nullable=False)


class TTSJob(Base):
    """Queued job claimed by worker-agents."""

    __tablename__ = "tts_jobs"
    __table_args__ = (
        Index("ix_tts_jobs_status_schedule", "status", "scheduled_at"),
        Index("ix_tts_jobs_owner_status", "owner_user_id", "status"),
        Index("ix_tts_jobs_target_worker_status", "target_worker_id", "status"),
        {"extend_existing": True},
    )

    id = Column(String, primary_key=True, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    target_worker_id = Column(Integer, ForeignKey("workers.id"), nullable=True, index=True)
    assigned_worker_id = Column(Integer, ForeignKey("workers.id"), nullable=True, index=True)
    provider = Column(String, nullable=False, index=True)
    text = Column(String, nullable=False)
    voice = Column(String, nullable=True)
    payload = Column(JsonType, nullable=False, default=dict)
    result_payload = Column(JsonType, nullable=False, default=dict)
    status = Column(String, nullable=False, default="queued", index=True)
    result_audio_url = Column(String, nullable=True)
    error_code = Column(String, nullable=True)
    error_message = Column(String, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    scheduled_at = Column(DateTime, default=utcnow_naive, nullable=False, index=True)
    lease_expires_at = Column(DateTime, nullable=True, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow_naive, nullable=False)
    updated_at = Column(DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=False)


class TTSJobAttempt(Base):
    """Attempt log for worker claimed jobs."""

    __tablename__ = "tts_job_attempts"
    __table_args__ = (
        Index("ix_tts_job_attempts_job_attempt", "job_id", "attempt_number"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, ForeignKey("tts_jobs.id"), nullable=False, index=True)
    worker_id = Column(Integer, ForeignKey("workers.id"), nullable=True, index=True)
    provider = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="leased", index=True)
    attempt_number = Column(Integer, nullable=False, default=1)
    error_code = Column(String, nullable=True)
    error_message = Column(String, nullable=True)
    result_audio_url = Column(String, nullable=True)
    started_at = Column(DateTime, default=utcnow_naive, nullable=False)
    finished_at = Column(DateTime, nullable=True)
