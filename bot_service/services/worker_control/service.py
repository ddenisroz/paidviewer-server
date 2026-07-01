"""Backend control plane for worker-based TTS execution."""

from __future__ import annotations

import asyncio
import base64
import uuid
from datetime import timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from core.config import settings
from core.datetime_utils import format_iso, utcnow_naive
from core.project_paths import TEMP_DIR
from models.user import User
from models.worker import TTSJob, Worker, WorkerPairingToken
from repositories.tts_job_repository import TTSJobRepository
from repositories.worker_repository import WorkerRepository
from services.tts.provider_audio import persist_audio_bytes
from services.worker_control.tokens import (
    generate_pairing_code,
    generate_secret_urlsafe,
    generate_worker_key,
    hash_secret,
)


class WorkerControlPlaneError(Exception):
    """Base error for worker control-plane operations."""


class WorkerAuthError(WorkerControlPlaneError):
    """Raised when a worker-agent token is invalid."""


class WorkerNotFoundError(WorkerControlPlaneError):
    """Raised when a worker or job does not exist."""


class WorkerConflictError(WorkerControlPlaneError):
    """Raised when the requested worker action conflicts with current state."""


class WorkerPermissionError(WorkerControlPlaneError):
    """Raised when the caller is not allowed to perform the action."""


class WorkerValidationError(WorkerControlPlaneError):
    """Raised when the request payload is invalid."""


class WorkerControlPlaneService:
    """Service layer for pairing, worker lifecycle and PostgreSQL-backed jobs."""

    def __init__(self, db: Session):
        self.db = db
        self.worker_repo = WorkerRepository(db)
        self.job_repo = TTSJobRepository(db)

    @staticmethod
    def _normalize_provider(provider: Optional[str], *, allow_both: bool = False) -> Optional[str]:
        normalized = str(provider or "").strip().lower()
        if not normalized:
            return None
        allowed = {"f5"}
        if normalized not in allowed:
            allowed_list = ", ".join(sorted(allowed))
            raise WorkerValidationError(f"provider must be one of: {allowed_list}")
        return normalized

    @staticmethod
    def _clean_text(value: Optional[str], *, field_name: str, max_length: int = 5000) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            raise WorkerValidationError(f"{field_name} is required")
        if len(cleaned) > max_length:
            raise WorkerValidationError(f"{field_name} exceeds {max_length} characters")
        return cleaned

    @staticmethod
    def _coerce_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def _require_user_exists(self, user_id: Optional[int]) -> Optional[int]:
        if user_id is None:
            return None
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise WorkerValidationError(f"user_id={user_id} was not found")
        return int(user_id)

    def _derive_provider_support(
        self,
        *,
        supports_f5: Optional[bool],
        capabilities: Optional[dict[str, Any]],
        provider_hint: Optional[str] = None,
    ) -> bool:
        capabilities = capabilities or {}
        providers = {
            str(item).strip().lower()
            for item in (capabilities.get("providers") or [])
            if str(item).strip()
        }
        derived_f5 = supports_f5 if supports_f5 is not None else ("f5" in providers)

        if not derived_f5:
            raise WorkerValidationError("worker must support F5")

        hinted_provider = self._normalize_provider(provider_hint)
        if hinted_provider == "f5" and not derived_f5:
            raise WorkerValidationError("pairing token requires F5 support")

        return bool(derived_f5)

    def _stale_before(self):
        return utcnow_naive() - timedelta(seconds=settings.worker_stale_after_seconds)

    def _mark_stale_workers_offline(self) -> None:
        stale_before = self._stale_before()
        stale_workers = (
            self.db.query(Worker)
            .filter(
                Worker.is_active.is_(True),
                Worker.status.in_(("online", "busy")),
                Worker.last_seen_at.is_not(None),
                Worker.last_seen_at < stale_before,
            )
            .all()
        )
        if not stale_workers:
            return
        for worker in stale_workers:
            worker.status = "offline"
        self.db.commit()

    def _effective_worker_status(self, worker: Worker) -> str:
        if not worker.is_active:
            if worker.status == "deleted":
                return "deleted"
            return "disabled"
        if worker.status in {"disabled", "deleted"}:
            return worker.status
        if worker.last_seen_at and worker.last_seen_at < self._stale_before():
            return "offline"
        return worker.status or "offline"

    @staticmethod
    def _worker_supports_provider(worker: Worker, provider: str) -> bool:
        _ = provider
        return bool(worker.supports_f5)

    @staticmethod
    def _serialize_worker(worker: Worker, *, effective_status: Optional[str] = None) -> dict[str, Any]:
        status_value = effective_status or worker.status or "offline"
        supported_providers = ["f5"] if worker.supports_f5 else []

        return {
            "id": worker.id,
            "worker_key": worker.worker_key,
            "label": worker.label,
            "owner_user_id": worker.owner_user_id,
            "is_active": bool(worker.is_active),
            "is_managed": bool(worker.is_managed),
            "status": status_value,
            "supports_f5": bool(worker.supports_f5),
            "providers": supported_providers,
            "capabilities": dict(worker.capabilities or {}),
            "runtime_metadata": dict(worker.runtime_metadata or {}),
            "last_seen_at": format_iso(worker.last_seen_at) if worker.last_seen_at else None,
            "last_error": worker.last_error,
            "created_at": format_iso(worker.created_at) if worker.created_at else None,
            "updated_at": format_iso(worker.updated_at) if worker.updated_at else None,
        }

    @staticmethod
    def _serialize_job(job: TTSJob) -> dict[str, Any]:
        return {
            "id": job.id,
            "owner_user_id": job.owner_user_id,
            "created_by_user_id": job.created_by_user_id,
            "target_worker_id": job.target_worker_id,
            "assigned_worker_id": job.assigned_worker_id,
            "provider": job.provider,
            "text": job.text,
            "voice": job.voice,
            "payload": dict(job.payload or {}),
            "result_payload": dict(job.result_payload or {}),
            "status": job.status,
            "result_audio_url": job.result_audio_url,
            "error_code": job.error_code,
            "error_message": job.error_message,
            "attempt_count": int(job.attempt_count or 0),
            "max_attempts": int(job.max_attempts or 0),
            "scheduled_at": format_iso(job.scheduled_at) if job.scheduled_at else None,
            "lease_expires_at": format_iso(job.lease_expires_at) if job.lease_expires_at else None,
            "started_at": format_iso(job.started_at) if job.started_at else None,
            "completed_at": format_iso(job.completed_at) if job.completed_at else None,
            "created_at": format_iso(job.created_at) if job.created_at else None,
            "updated_at": format_iso(job.updated_at) if job.updated_at else None,
        }

    def _touch_worker(
        self,
        worker: Worker,
        *,
        status: str,
        capabilities: Optional[dict[str, Any]] = None,
        runtime_metadata: Optional[dict[str, Any]] = None,
        supports_f5: Optional[bool] = None,
        last_error: Optional[str] = None,
    ) -> Worker:
        worker.last_seen_at = utcnow_naive()
        worker.status = status
        if capabilities is not None:
            worker.capabilities = dict(capabilities)
        if runtime_metadata is not None:
            worker.runtime_metadata = dict(runtime_metadata)
        if supports_f5 is not None:
            worker.supports_f5 = bool(supports_f5)
        if last_error is not None:
            worker.last_error = last_error.strip() or None
        self.db.add(worker)
        self.db.commit()
        self.db.refresh(worker)
        return worker

    def issue_pairing_token(
        self,
        *,
        owner_user_id: Optional[int],
        label_hint: Optional[str],
        provider_hint: Optional[str],
        is_managed: bool,
    ) -> dict[str, Any]:
        normalized_provider_hint = self._normalize_provider(provider_hint)
        resolved_owner_user_id = self._require_user_exists(owner_user_id)
        if not is_managed and resolved_owner_user_id is None:
            raise WorkerValidationError("owner_user_id is required for self-hosted pairing tokens")

        raw_token = generate_pairing_code()
        expires_at = utcnow_naive() + timedelta(minutes=settings.worker_pairing_token_ttl_minutes)

        token = WorkerPairingToken(
            owner_user_id=resolved_owner_user_id,
            token_hash=hash_secret(raw_token),
            label_hint=str(label_hint or "").strip() or None,
            provider_hint=normalized_provider_hint,
            is_managed=bool(is_managed),
            expires_at=expires_at,
        )
        self.db.add(token)
        self.db.commit()
        self.db.refresh(token)

        return {
            "pairing_code": raw_token,
            "expires_at": format_iso(expires_at),
            "label_hint": token.label_hint,
            "provider_hint": token.provider_hint,
            "is_managed": bool(token.is_managed),
            "owner_user_id": token.owner_user_id,
        }

    def activate_worker(
        self,
        *,
        pairing_code: str,
        label: Optional[str],
        supports_f5: Optional[bool],
        capabilities: Optional[dict[str, Any]],
        runtime_metadata: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        pairing_code = self._clean_text(pairing_code, field_name="pairing_code", max_length=256)
        token = self.worker_repo.get_pairing_token(pairing_code)
        now = utcnow_naive()
        if not token:
            raise WorkerValidationError("pairing code is invalid")
        if token.used_at is not None:
            raise WorkerValidationError("pairing code has already been used")
        if token.expires_at < now:
            raise WorkerValidationError("pairing code has expired")

        resolved_supports_f5 = self._derive_provider_support(
            supports_f5=supports_f5,
            capabilities=capabilities,
            provider_hint=token.provider_hint,
        )

        auth_token = generate_secret_urlsafe(48)
        worker = Worker(
            worker_key=generate_worker_key(),
            owner_user_id=token.owner_user_id,
            label=str(label or token.label_hint or "TTS Worker").strip() or "TTS Worker",
            auth_token_hash=hash_secret(auth_token),
            supports_f5=resolved_supports_f5,
            capabilities=dict(capabilities or {}),
            runtime_metadata=dict(runtime_metadata or {}),
            status="online",
            last_seen_at=now,
            is_active=True,
            is_managed=bool(token.is_managed),
        )

        token.used_at = now
        self.db.add(worker)
        self.db.add(token)
        self.db.commit()
        self.db.refresh(worker)

        return {
            "worker": self._serialize_worker(worker, effective_status="online"),
            "auth_token": auth_token,
        }

    def authenticate_worker(self, authorization_header: Optional[str]) -> Worker:
        auth_header = str(authorization_header or "").strip()
        if not auth_header.lower().startswith("bearer "):
            raise WorkerAuthError("missing bearer token")

        raw_token = auth_header.split(" ", 1)[1].strip()
        if not raw_token:
            raise WorkerAuthError("missing bearer token")

        worker = self.worker_repo.get_by_auth_token(raw_token)
        if not worker:
            raise WorkerAuthError("invalid worker token")
        if not worker.is_active or worker.status == "deleted":
            raise WorkerAuthError("worker is inactive")
        return worker

    def _reload_worker(self, worker: Worker) -> Worker:
        current_worker = self.db.query(Worker).filter(Worker.id == worker.id).first()
        if not current_worker:
            raise WorkerAuthError("worker no longer exists")
        if not current_worker.is_active or current_worker.status == "deleted":
            raise WorkerAuthError("worker is inactive")
        return current_worker

    def list_workers_for_user(self, owner_user_id: int) -> list[dict[str, Any]]:
        self._mark_stale_workers_offline()
        workers = [
            worker
            for worker in self.worker_repo.list_for_user(owner_user_id)
            if worker.status != "deleted"
        ]
        return [
            self._serialize_worker(worker, effective_status=self._effective_worker_status(worker))
            for worker in workers
        ]

    def list_workers_admin(self) -> list[dict[str, Any]]:
        self._mark_stale_workers_offline()
        workers = (
            self.db.query(Worker)
            .filter(Worker.status != "deleted")
            .order_by(Worker.created_at.desc())
            .all()
        )
        return [
            self._serialize_worker(worker, effective_status=self._effective_worker_status(worker))
            for worker in workers
        ]

    def get_preferred_worker(
        self,
        *,
        provider: str,
        owner_user_id: Optional[int] = None,
        managed_only: bool = False,
    ) -> Optional[Worker]:
        normalized_provider = self._normalize_provider(provider) or "f5"
        self._mark_stale_workers_offline()

        query = self.db.query(Worker).filter(
            Worker.is_active.is_(True),
            Worker.status.in_(("online", "busy")),
        )
        if managed_only:
            query = query.filter(Worker.is_managed.is_(True))
        else:
            if owner_user_id is None:
                raise WorkerValidationError("owner_user_id is required for self-hosted worker selection")
            query = query.filter(
                Worker.is_managed.is_(False),
                Worker.owner_user_id == owner_user_id,
            )

        candidates = query.order_by(Worker.last_seen_at.desc(), Worker.created_at.desc()).all()
        preferred_status_order = {"online": 0, "busy": 1}
        ranked_candidates = [
            candidate
            for candidate in candidates
            if self._worker_supports_provider(candidate, normalized_provider)
        ]
        ranked_candidates.sort(
            key=lambda worker: (
                worker.last_seen_at or worker.created_at or utcnow_naive(),
                int(worker.id or 0),
            ),
            reverse=True,
        )
        ranked_candidates.sort(key=lambda worker: preferred_status_order.get(self._effective_worker_status(worker), 99))
        return ranked_candidates[0] if ranked_candidates else None

    def reconcile_workers_and_jobs(self) -> dict[str, int]:
        self._mark_stale_workers_offline()
        requeued_jobs = self.job_repo.requeue_expired_jobs(max_attempts=settings.worker_job_max_attempts)
        return {"requeued_jobs": int(requeued_jobs)}

    def _get_user_worker(self, *, owner_user_id: int, worker_key: str) -> Worker:
        worker = self.worker_repo.get_for_user(owner_user_id, worker_key)
        if not worker or worker.status == "deleted":
            raise WorkerNotFoundError("worker not found")
        return worker

    def _get_any_worker(self, *, worker_key: str) -> Worker:
        worker = self.worker_repo.get_by_worker_key(worker_key)
        if not worker or worker.status == "deleted":
            raise WorkerNotFoundError("worker not found")
        return worker

    def disable_worker_for_user(self, *, owner_user_id: int, worker_key: str) -> dict[str, Any]:
        worker = self._get_user_worker(owner_user_id=owner_user_id, worker_key=worker_key)
        self.job_repo.release_jobs_for_worker(
            worker.id,
            error_code="worker_disabled",
            error_message="Target worker was disabled and queued jobs were released",
        )
        worker.is_active = False
        worker.status = "disabled"
        worker.last_error = None
        self.db.add(worker)
        self.db.commit()
        self.db.refresh(worker)
        return self._serialize_worker(worker, effective_status="disabled")

    def delete_worker_for_user(self, *, owner_user_id: int, worker_key: str) -> None:
        worker = self._get_user_worker(owner_user_id=owner_user_id, worker_key=worker_key)
        self.job_repo.release_jobs_for_worker(
            worker.id,
            error_code="worker_deleted",
            error_message="Target worker was deleted and queued jobs were released",
        )
        worker.is_active = False
        worker.status = "deleted"
        self.db.add(worker)
        self.db.commit()

    def disable_worker_admin(self, *, worker_key: str) -> dict[str, Any]:
        worker = self._get_any_worker(worker_key=worker_key)
        self.job_repo.release_jobs_for_worker(
            worker.id,
            error_code="worker_disabled",
            error_message="Target worker was disabled by administrator and queued jobs were released",
        )
        worker.is_active = False
        worker.status = "disabled"
        self.db.add(worker)
        self.db.commit()
        self.db.refresh(worker)
        return self._serialize_worker(worker, effective_status="disabled")

    def delete_worker_admin(self, *, worker_key: str) -> None:
        worker = self._get_any_worker(worker_key=worker_key)
        self.job_repo.release_jobs_for_worker(
            worker.id,
            error_code="worker_deleted",
            error_message="Target worker was deleted by administrator and queued jobs were released",
        )
        worker.is_active = False
        worker.status = "deleted"
        self.db.add(worker)
        self.db.commit()

    def enqueue_job(
        self,
        *,
        provider: str,
        text: str,
        voice: Optional[str],
        payload: Optional[dict[str, Any]],
        owner_user_id: Optional[int],
        created_by_user_id: Optional[int],
        target_worker_key: Optional[str],
        require_managed_target: bool = False,
        max_attempts: Optional[int] = None,
    ) -> dict[str, Any]:
        normalized_provider = self._normalize_provider(provider) or "f5"
        cleaned_text = self._clean_text(text, field_name="text")
        resolved_owner_user_id = self._require_user_exists(owner_user_id)

        target_worker_id: Optional[int] = None
        if target_worker_key:
            worker = self._get_any_worker(worker_key=self._clean_text(target_worker_key, field_name="target_worker_key"))
            if not worker.is_active:
                raise WorkerConflictError("target worker is inactive")
            if require_managed_target and not worker.is_managed:
                raise WorkerValidationError("target worker must be managed")
            if not require_managed_target and resolved_owner_user_id is not None and worker.owner_user_id != resolved_owner_user_id:
                raise WorkerPermissionError("target worker does not belong to this user")
            if normalized_provider == "f5" and not worker.supports_f5:
                raise WorkerValidationError("target worker does not support F5")
            target_worker_id = worker.id

        job = TTSJob(
            id=uuid.uuid4().hex,
            owner_user_id=resolved_owner_user_id,
            created_by_user_id=created_by_user_id,
            target_worker_id=target_worker_id,
            provider=normalized_provider,
            text=cleaned_text,
            voice=str(voice or "").strip() or None,
            payload=dict(payload or {}),
            status="queued",
            max_attempts=max_attempts or settings.worker_job_max_attempts,
        )
        created_job = self.job_repo.create_job(job)
        return self._serialize_job(created_job)

    def get_job_for_user(self, *, owner_user_id: int, job_id: str) -> dict[str, Any]:
        job = self.job_repo.get_job_for_user(self._clean_text(job_id, field_name="job_id"), owner_user_id)
        if not job:
            raise WorkerNotFoundError("job not found")
        return self._serialize_job(job)

    def get_job_admin(self, *, job_id: str) -> dict[str, Any]:
        job = self.job_repo.get_job(self._clean_text(job_id, field_name="job_id"))
        if not job:
            raise WorkerNotFoundError("job not found")
        return self._serialize_job(job)

    async def wait_for_job_terminal_state(
        self,
        *,
        job_id: str,
        timeout_seconds: Optional[int] = None,
        poll_interval_seconds: Optional[int] = None,
    ) -> dict[str, Any]:
        normalized_job_id = self._clean_text(job_id, field_name="job_id")
        timeout_seconds = max(1, int(timeout_seconds or settings.worker_result_timeout_seconds))
        poll_interval_seconds = max(1, int(poll_interval_seconds or settings.worker_result_poll_interval_seconds))
        deadline = utcnow_naive() + timedelta(seconds=timeout_seconds)

        while utcnow_naive() <= deadline:
            self.job_repo.requeue_expired_jobs(max_attempts=settings.worker_job_max_attempts)
            self.db.expire_all()
            job = self.job_repo.get_job(normalized_job_id)
            if not job:
                raise WorkerNotFoundError("job not found")
            if job.status in {"completed", "failed"}:
                return self._serialize_job(job)
            await asyncio.sleep(poll_interval_seconds)

        self.db.expire_all()
        job = self.job_repo.get_job(normalized_job_id)
        if not job:
            raise WorkerNotFoundError("job not found")
        if job.status not in {"completed", "failed"}:
            now = utcnow_naive()
            attempt = self.job_repo.get_open_attempt(job.id, job.attempt_count)
            if attempt:
                attempt.status = "timed_out"
                attempt.error_code = "result_timeout"
                attempt.error_message = "Synchronous bot_service request timed out while waiting for worker result"
                attempt.finished_at = now
            job.status = "failed"
            job.completed_at = now
            job.lease_expires_at = None
            job.error_code = "result_timeout"
            job.error_message = "Synchronous bot_service request timed out while waiting for worker result"
            self.db.add(job)
            self.db.commit()
            self.db.refresh(job)
        return self._serialize_job(job)

    async def synthesize_via_worker(
        self,
        *,
        provider: str,
        text: str,
        voice: Optional[str],
        payload: Optional[dict[str, Any]],
        owner_user_id: Optional[int],
        created_by_user_id: Optional[int],
        managed_only: bool,
        timeout_seconds: Optional[int] = None,
    ) -> Optional[dict[str, Any]]:
        normalized_provider = self._normalize_provider(provider) or "f5"
        available_worker = self.get_preferred_worker(
            provider=normalized_provider,
            owner_user_id=owner_user_id,
            managed_only=managed_only,
        )
        if not available_worker:
            return None

        job = self.enqueue_job(
            provider=normalized_provider,
            text=text,
            voice=voice,
            payload=payload,
            owner_user_id=None if managed_only else owner_user_id,
            created_by_user_id=created_by_user_id,
            target_worker_key=None,
            require_managed_target=False,
        )
        final_job = await self.wait_for_job_terminal_state(
            job_id=job["id"],
            timeout_seconds=timeout_seconds,
        )
        assigned_worker = None
        assigned_worker_id = final_job.get("assigned_worker_id")
        if assigned_worker_id:
            assigned_worker = self.db.query(Worker).filter(Worker.id == assigned_worker_id).first()
        resolved_worker = assigned_worker or available_worker
        final_job["worker_key"] = resolved_worker.worker_key
        final_job["worker_label"] = resolved_worker.label
        final_job["worker_mode"] = "managed" if managed_only else "self_hosted"
        return final_job

    def poll_worker_jobs(
        self,
        *,
        worker: Worker,
        max_jobs: int,
        supports_f5: Optional[bool],
        capabilities: Optional[dict[str, Any]],
        runtime_metadata: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        worker = self._reload_worker(worker)

        resolved_supports_f5 = self._derive_provider_support(
            supports_f5=supports_f5 if supports_f5 is not None else worker.supports_f5,
            capabilities=capabilities if capabilities is not None else dict(worker.capabilities or {}),
            provider_hint=None,
        )
        self.job_repo.requeue_expired_jobs(max_attempts=settings.worker_job_max_attempts)
        claimed_jobs = self.job_repo.claim_jobs(
            worker=worker,
            max_jobs=max(1, min(int(max_jobs or 1), 10)),
            lease_seconds=settings.worker_job_lease_seconds,
            max_attempts=settings.worker_job_max_attempts,
        )

        updated_worker = self._touch_worker(
            worker,
            status="busy" if claimed_jobs else "online",
            capabilities=capabilities if capabilities is not None else dict(worker.capabilities or {}),
            runtime_metadata=runtime_metadata if runtime_metadata is not None else dict(worker.runtime_metadata or {}),
            supports_f5=resolved_supports_f5,
            last_error="",
        )
        return {
            "worker": self._serialize_worker(updated_worker, effective_status=self._effective_worker_status(updated_worker)),
            "jobs": [self._serialize_job(job) for job in claimed_jobs],
            "lease_seconds": settings.worker_job_lease_seconds,
        }

    def _get_job_for_worker(self, *, worker: Worker, job_id: str) -> TTSJob:
        job = self.job_repo.get_job(self._clean_text(job_id, field_name="job_id"))
        if not job:
            raise WorkerNotFoundError("job not found")
        if job.assigned_worker_id != worker.id:
            raise WorkerPermissionError("job is not assigned to this worker")
        return job

    @staticmethod
    def _decode_audio_payload(audio_base64: str) -> bytes:
        cleaned = str(audio_base64 or "").strip()
        if not cleaned:
            raise WorkerValidationError("audio_base64 is required")
        if "," in cleaned and cleaned.lower().startswith("data:"):
            cleaned = cleaned.split(",", 1)[1].strip()
        try:
            audio_bytes = base64.b64decode(cleaned, validate=True)
        except Exception as error:
            raise WorkerValidationError(f"audio_base64 is invalid: {error}") from error
        if not audio_bytes:
            raise WorkerValidationError("decoded audio payload is empty")
        return audio_bytes

    async def complete_job(
        self,
        *,
        worker: Worker,
        job_id: str,
        audio_base64: Optional[str],
        content_type: Optional[str],
        source_url: Optional[str],
        result_payload: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        worker = self._reload_worker(worker)
        job = self._get_job_for_worker(worker=worker, job_id=job_id)
        if job.status == "completed":
            return self._serialize_job(job)
        if job.status != "leased":
            raise WorkerConflictError(f"job status must be leased, got {job.status}")

        audio_bytes = self._decode_audio_payload(audio_base64 or "")
        persisted = await persist_audio_bytes(
            audio_bytes=audio_bytes,
            provider=job.provider,
            source_url=source_url,
            content_type=content_type or "audio/wav",
            backend_url=settings.backend_url.rstrip("/"),
            temp_dir=TEMP_DIR,
        )
        merged_result_payload = dict(result_payload or {})
        merged_result_payload.setdefault("provider", job.provider)
        merged_result_payload.setdefault("audio_path", persisted.get("audio_path"))

        completed_job = self.job_repo.complete_job(
            job=job,
            worker=worker,
            result_audio_url=persisted.get("audio_url"),
            result_payload=merged_result_payload,
        )
        self._touch_worker(worker, status="online", last_error="")
        return self._serialize_job(completed_job)

    def fail_job(
        self,
        *,
        worker: Worker,
        job_id: str,
        error_code: Optional[str],
        error_message: Optional[str],
        retryable: bool,
    ) -> dict[str, Any]:
        worker = self._reload_worker(worker)
        job = self._get_job_for_worker(worker=worker, job_id=job_id)
        if job.status == "completed":
            raise WorkerConflictError("completed job cannot be failed")
        if job.status != "leased":
            raise WorkerConflictError(f"job status must be leased, got {job.status}")

        failed_job = self.job_repo.fail_job(
            job=job,
            worker=worker,
            error_code=str(error_code or "worker_failed").strip() or "worker_failed",
            error_message=self._clean_text(
                error_message or "worker reported failure",
                field_name="error_message",
                max_length=2000,
            ),
            retryable=bool(retryable),
            max_attempts=settings.worker_job_max_attempts,
        )
        self._touch_worker(
            worker,
            status="online",
            last_error=failed_job.error_message,
        )
        return self._serialize_job(failed_job)
