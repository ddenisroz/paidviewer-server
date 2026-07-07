"""Backend-only worker control-plane routes for F5 agents."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.auth import get_admin_user, get_current_user
from core.config import settings
from core.database import get_db
from repositories.local_tts_repository import LocalTTSRepository
from services.worker_control.service import (
    WorkerAuthError,
    WorkerConflictError,
    WorkerControlPlaneError,
    WorkerControlPlaneService,
    WorkerNotFoundError,
    WorkerPermissionError,
    WorkerValidationError,
)


logger = logging.getLogger("bot_service.tts.worker_control")

worker_router = APIRouter(prefix="/api/tts", tags=["tts-workers"])
worker_agent_router = APIRouter(prefix="/api/worker-agent", tags=["worker-agent"])


def _parse_version_parts(value: str) -> tuple[int, ...]:
    cleaned = str(value or "").strip()
    if not cleaned:
        return tuple()
    parts: list[int] = []
    for token in cleaned.split("."):
        digits = "".join(ch for ch in token if ch.isdigit())
        parts.append(int(digits or "0"))
    return tuple(parts)


def _is_agent_version_compatible(current_version: str, required_version: str) -> bool:
    required_parts = _parse_version_parts(required_version)
    current_parts = _parse_version_parts(current_version)
    if not required_parts:
        return True
    if not current_parts:
        return False

    max_len = max(len(required_parts), len(current_parts))
    normalized_required = required_parts + (0,) * (max_len - len(required_parts))
    normalized_current = current_parts + (0,) * (max_len - len(current_parts))
    return normalized_current >= normalized_required


def _resolve_agent_version(runtime_metadata: dict[str, Any], capabilities: dict[str, Any]) -> str:
    for payload in (runtime_metadata or {}, capabilities or {}):
        agent_version = str(payload.get("agent_version") or "").strip()
        if agent_version:
            return agent_version
    return ""


class PairingTokenRequest(BaseModel):
    label_hint: Optional[str] = Field(default=None, max_length=120)
    provider_hint: Optional[str] = Field(default=None, max_length=16)


class AdminPairingTokenRequest(PairingTokenRequest):
    owner_user_id: Optional[int] = None
    is_managed: bool = True


class ManualWorkerJobRequest(BaseModel):
    provider: str = Field(..., min_length=2, max_length=16)
    text: str = Field(..., min_length=1, max_length=5000)
    voice: Optional[str] = Field(default=None, max_length=255)
    payload: dict[str, Any] = Field(default_factory=dict)
    target_worker_key: Optional[str] = Field(default=None, max_length=128)
    max_attempts: Optional[int] = Field(default=None, ge=1, le=10)


class WorkerActivationRequest(BaseModel):
    pairing_code: str = Field(..., min_length=3, max_length=256)
    label: Optional[str] = Field(default=None, max_length=120)
    supports_f5: Optional[bool] = None
    capabilities: dict[str, Any] = Field(default_factory=dict)
    runtime_metadata: dict[str, Any] = Field(default_factory=dict)


class WorkerPollRequest(BaseModel):
    max_jobs: int = Field(default=1, ge=1, le=10)
    wait_for_jobs: bool = True
    supports_f5: Optional[bool] = None
    capabilities: dict[str, Any] = Field(default_factory=dict)
    runtime_metadata: dict[str, Any] = Field(default_factory=dict)


class WorkerCompleteRequest(BaseModel):
    audio_base64: str = Field(..., min_length=8)
    content_type: Optional[str] = Field(default=None, max_length=120)
    source_url: Optional[str] = Field(default=None, max_length=1000)
    result_payload: dict[str, Any] = Field(default_factory=dict)


class WorkerFailRequest(BaseModel):
    error_code: Optional[str] = Field(default=None, max_length=120)
    error_message: str = Field(..., min_length=1, max_length=2000)
    retryable: bool = True


def _resolve_server_base_url(request: Request) -> str:
    forwarded_proto = str(request.headers.get("x-forwarded-proto") or "").split(",", maxsplit=1)[0].strip().lower()
    forwarded_host = str(request.headers.get("x-forwarded-host") or "").split(",", maxsplit=1)[0].strip()
    if forwarded_proto in {"http", "https"} and forwarded_host:
        forwarded_origin = _normalize_origin(f"{forwarded_proto}://{forwarded_host}")
        if forwarded_origin:
            return forwarded_origin

    configured_url = str(settings.backend_url or "").strip().rstrip("/")
    configured_origin = _normalize_origin(configured_url)
    if configured_origin:
        configured_host = (urlparse(configured_origin).hostname or "").strip().lower()
        if configured_host not in {"localhost", "127.0.0.1", "0.0.0.0", "testserver"}:
            return configured_origin

    request_base_url = str(request.base_url or "").strip().rstrip("/")
    if request_base_url:
        return request_base_url
    if configured_origin:
        return configured_origin
    return "http://127.0.0.1:8000"


def _resolve_default_provider_endpoint(provider: str) -> str:
    return str(settings.worker_agent_default_f5_endpoint_url or "").strip() or "http://127.0.0.1:8011"


def _build_provisioning_bundle(
    *,
    server_base_url: str,
    pairing_payload: dict[str, Any],
    trusted_origins: list[str],
    provider_endpoint_url: Optional[str] = None,
    provider_api_key: Optional[str] = None,
) -> dict[str, Any]:
    label_hint = str(pairing_payload.get("label_hint") or "").strip() or "My TTS Worker"

    return {
        "kind": "paidviewer_worker_provisioning",
        "format_version": 1,
        "server_base_url": server_base_url,
        "pairing_code": pairing_payload.get("pairing_code"),
        "expires_at": pairing_payload.get("expires_at"),
        "required_agent_version": str(settings.tts_worker_agent_required_version or "").strip() or None,
        "recommended_agent_version": str(
            settings.tts_worker_agent_recommended_version or settings.tts_worker_agent_required_version or ""
        ).strip() or None,
        "trusted_origins": trusted_origins,
        "label": label_hint,
        "poll_interval_sec": 2,
        "max_jobs_per_poll": 1,
        "wait_for_jobs": True,
        "providers": {
            "f5": {
                "enabled": True,
                "endpoint_url": provider_endpoint_url or _resolve_default_provider_endpoint("f5"),
                "api_key": provider_api_key or "",
            },
        },
    }


def _get_saved_provider_runtime_config(
    *,
    db: Session,
    user_id: int,
    provider: str,
) -> tuple[Optional[str], Optional[str]]:
    try:
        config = LocalTTSRepository(db).get_by_user_id(user_id, provider=provider)
    except Exception:
        logger.exception("Failed to read saved %s local runtime config for provisioning", provider)
        return None, None
    if not config:
        return None, None
    endpoint_url = str(getattr(config, "endpoint_url", "") or "").strip() or None
    api_key = str(getattr(config, "api_key", "") or "").strip() or None
    return endpoint_url, api_key


def _build_provisioning_filename(provider_hint: Optional[str]) -> str:
    normalized_provider = str(provider_hint or "").strip().lower() or "f5"
    provider_slug = normalized_provider if normalized_provider == "f5" else "f5"
    timestamp = int(time.time())
    return f"paidviewer-worker-provisioning-{provider_slug}-{timestamp}.json"


def _normalize_origin(value: Optional[str]) -> Optional[str]:
    raw_value = str(value or "").strip()
    if not raw_value:
        return None
    parsed = urlparse(raw_value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _resolve_trusted_origins(request: Request, server_base_url: str) -> list[str]:
    candidates = [
        _normalize_origin(request.headers.get("origin")),
        _normalize_origin(settings.frontend_url),
        _normalize_origin(server_base_url),
    ]

    for configured_origin in settings.cors_origins_list:
        candidates.append(_normalize_origin(configured_origin))

    if settings.is_development or settings.testing:
        candidates.extend(
            [
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://localhost:3000",
                "http://127.0.0.1:3000",
            ]
        )

    resolved: list[str] = []
    for candidate in candidates:
        if not candidate or candidate in resolved:
            continue
        resolved.append(candidate)
    return resolved


def get_worker_control_service(db: Session = Depends(get_db)) -> WorkerControlPlaneService:
    return WorkerControlPlaneService(db)


def _raise_worker_http_error(error: Exception) -> None:
    if isinstance(error, WorkerAuthError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    if isinstance(error, WorkerPermissionError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    if isinstance(error, WorkerNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    if isinstance(error, WorkerConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    if isinstance(error, WorkerValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    if isinstance(error, WorkerControlPlaneError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)) from error
    raise error


def _require_worker_agent(
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    service: WorkerControlPlaneService = Depends(get_worker_control_service),
):
    try:
        return service.authenticate_worker(authorization)
    except Exception as error:
        _raise_worker_http_error(error)


@worker_router.get("/workers")
async def list_user_workers(
    user: dict = Depends(get_current_user),
    service: WorkerControlPlaneService = Depends(get_worker_control_service),
):
    try:
        return {"success": True, "workers": service.list_workers_for_user(int(user["id"]))}
    except Exception as error:
        _raise_worker_http_error(error)


@worker_router.post("/workers/pairing-tokens")
async def create_pairing_token(
    request: PairingTokenRequest,
    user: dict = Depends(get_current_user),
    service: WorkerControlPlaneService = Depends(get_worker_control_service),
):
    try:
        payload = service.issue_pairing_token(
            owner_user_id=int(user["id"]),
            label_hint=request.label_hint,
            provider_hint=request.provider_hint,
            is_managed=False,
        )
        return {"success": True, **payload}
    except Exception as error:
        _raise_worker_http_error(error)


@worker_router.post("/workers/provisioning")
async def create_worker_provisioning_bundle(
    request: PairingTokenRequest,
    http_request: Request,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    service: WorkerControlPlaneService = Depends(get_worker_control_service),
):
    try:
        pairing_payload = service.issue_pairing_token(
            owner_user_id=int(user["id"]),
            label_hint=request.label_hint,
            provider_hint=request.provider_hint,
            is_managed=False,
        )
        server_base_url = _resolve_server_base_url(http_request)
        trusted_origins = _resolve_trusted_origins(http_request, server_base_url)
        provider_endpoint_url, provider_api_key = _get_saved_provider_runtime_config(
            db=db,
            user_id=int(user["id"]),
            provider="f5",
        )
        provisioning_bundle = _build_provisioning_bundle(
            server_base_url=server_base_url,
            pairing_payload=pairing_payload,
            trusted_origins=trusted_origins,
            provider_endpoint_url=provider_endpoint_url,
            provider_api_key=provider_api_key,
        )
        return {
            "success": True,
            "download_filename": _build_provisioning_filename(pairing_payload.get("provider_hint")),
            "provisioning_bundle": provisioning_bundle,
            "worker_agent_contract": {
                "official_mode": "self_host",
                "recommended_path": "tts_worker_agent",
                "required_agent_version": provisioning_bundle.get("required_agent_version"),
                "recommended_agent_version": provisioning_bundle.get("recommended_agent_version"),
                "legacy_raw_endpoint_supported": True,
            },
            **pairing_payload,
        }
    except Exception as error:
        _raise_worker_http_error(error)


@worker_router.post("/workers/jobs")
async def create_user_worker_job(
    request: ManualWorkerJobRequest,
    user: dict = Depends(get_current_user),
    service: WorkerControlPlaneService = Depends(get_worker_control_service),
):
    try:
        job = service.enqueue_job(
            provider=request.provider,
            text=request.text,
            voice=request.voice,
            payload=request.payload,
            owner_user_id=int(user["id"]),
            created_by_user_id=int(user["id"]),
            target_worker_key=request.target_worker_key,
            max_attempts=request.max_attempts,
        )
        return {"success": True, "job": job}
    except Exception as error:
        _raise_worker_http_error(error)


@worker_router.get("/workers/jobs/{job_id}")
async def get_user_worker_job(
    job_id: str,
    user: dict = Depends(get_current_user),
    service: WorkerControlPlaneService = Depends(get_worker_control_service),
):
    try:
        return {"success": True, "job": service.get_job_for_user(owner_user_id=int(user["id"]), job_id=job_id)}
    except Exception as error:
        _raise_worker_http_error(error)


@worker_router.post("/workers/{worker_key}/disable")
async def disable_user_worker(
    worker_key: str,
    user: dict = Depends(get_current_user),
    service: WorkerControlPlaneService = Depends(get_worker_control_service),
):
    try:
        worker = service.disable_worker_for_user(owner_user_id=int(user["id"]), worker_key=worker_key)
        return {"success": True, "worker": worker}
    except Exception as error:
        _raise_worker_http_error(error)


@worker_router.delete("/workers/{worker_key}")
async def delete_user_worker(
    worker_key: str,
    user: dict = Depends(get_current_user),
    service: WorkerControlPlaneService = Depends(get_worker_control_service),
):
    try:
        service.delete_worker_for_user(owner_user_id=int(user["id"]), worker_key=worker_key)
        return {"success": True}
    except Exception as error:
        _raise_worker_http_error(error)


@worker_router.get("/admin/workers")
async def list_admin_workers(
    _: dict = Depends(get_admin_user),
    service: WorkerControlPlaneService = Depends(get_worker_control_service),
):
    try:
        return {"success": True, "workers": service.list_workers_admin()}
    except Exception as error:
        _raise_worker_http_error(error)


@worker_router.post("/admin/workers/pairing-tokens")
async def create_admin_pairing_token(
    request: AdminPairingTokenRequest,
    _: dict = Depends(get_admin_user),
    service: WorkerControlPlaneService = Depends(get_worker_control_service),
):
    try:
        payload = service.issue_pairing_token(
            owner_user_id=request.owner_user_id,
            label_hint=request.label_hint,
            provider_hint=request.provider_hint,
            is_managed=bool(request.is_managed),
        )
        return {"success": True, **payload}
    except Exception as error:
        _raise_worker_http_error(error)


@worker_router.post("/admin/workers/jobs")
async def create_admin_worker_job(
    request: ManualWorkerJobRequest,
    admin: dict = Depends(get_admin_user),
    service: WorkerControlPlaneService = Depends(get_worker_control_service),
):
    try:
        job = service.enqueue_job(
            provider=request.provider,
            text=request.text,
            voice=request.voice,
            payload=request.payload,
            owner_user_id=None,
            created_by_user_id=int(admin["id"]),
            target_worker_key=request.target_worker_key,
            require_managed_target=bool(request.target_worker_key),
            max_attempts=request.max_attempts,
        )
        return {"success": True, "job": job}
    except Exception as error:
        _raise_worker_http_error(error)


@worker_router.get("/admin/workers/jobs/{job_id}")
async def get_admin_worker_job(
    job_id: str,
    _: dict = Depends(get_admin_user),
    service: WorkerControlPlaneService = Depends(get_worker_control_service),
):
    try:
        return {"success": True, "job": service.get_job_admin(job_id=job_id)}
    except Exception as error:
        _raise_worker_http_error(error)


@worker_router.post("/admin/workers/{worker_key}/disable")
async def disable_admin_worker(
    worker_key: str,
    _: dict = Depends(get_admin_user),
    service: WorkerControlPlaneService = Depends(get_worker_control_service),
):
    try:
        worker = service.disable_worker_admin(worker_key=worker_key)
        return {"success": True, "worker": worker}
    except Exception as error:
        _raise_worker_http_error(error)


@worker_router.delete("/admin/workers/{worker_key}")
async def delete_admin_worker(
    worker_key: str,
    _: dict = Depends(get_admin_user),
    service: WorkerControlPlaneService = Depends(get_worker_control_service),
):
    try:
        service.delete_worker_admin(worker_key=worker_key)
        return {"success": True}
    except Exception as error:
        _raise_worker_http_error(error)


@worker_agent_router.post("/activate")
async def activate_worker_agent(
    request: WorkerActivationRequest,
    service: WorkerControlPlaneService = Depends(get_worker_control_service),
):
    agent_version = _resolve_agent_version(request.runtime_metadata, request.capabilities)
    required_version = str(settings.tts_worker_agent_required_version or "").strip()
    if required_version and not _is_agent_version_compatible(agent_version, required_version):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "version_mismatch",
                "message": (
                    f"Worker agent version {agent_version or 'unknown'} is older than required version "
                    f"{required_version}."
                ),
                "required_agent_version": required_version,
                "current_agent_version": agent_version or None,
            },
        )
    try:
        payload = service.activate_worker(
            pairing_code=request.pairing_code,
            label=request.label,
            supports_f5=request.supports_f5,
            capabilities=request.capabilities,
            runtime_metadata=request.runtime_metadata,
        )
        return {
            "success": True,
            "required_agent_version": required_version or None,
            "recommended_agent_version": str(
                settings.tts_worker_agent_recommended_version or settings.tts_worker_agent_required_version or ""
            ).strip() or None,
            **payload,
        }
    except Exception as error:
        _raise_worker_http_error(error)


@worker_agent_router.post("/poll")
async def poll_worker_jobs(
    request: WorkerPollRequest,
    worker=Depends(_require_worker_agent),
    service: WorkerControlPlaneService = Depends(get_worker_control_service),
):
    agent_version = _resolve_agent_version(request.runtime_metadata, request.capabilities)
    required_version = str(settings.tts_worker_agent_required_version or "").strip()
    if required_version and not _is_agent_version_compatible(agent_version, required_version):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "version_mismatch",
                "message": (
                    f"Worker agent version {agent_version or 'unknown'} is older than required version "
                    f"{required_version}."
                ),
                "required_agent_version": required_version,
                "current_agent_version": agent_version or None,
            },
        )
    try:
        deadline = time.monotonic() + max(1, settings.worker_poll_timeout_seconds)
        while True:
            payload = service.poll_worker_jobs(
                worker=worker,
                max_jobs=request.max_jobs,
                supports_f5=request.supports_f5,
                capabilities=request.capabilities,
                runtime_metadata=request.runtime_metadata,
            )
            if payload["jobs"] or not request.wait_for_jobs or time.monotonic() >= deadline:
                return {
                    "success": True,
                    "required_agent_version": required_version or None,
                    "recommended_agent_version": str(
                        settings.tts_worker_agent_recommended_version or settings.tts_worker_agent_required_version or ""
                    ).strip() or None,
                    **payload,
                }
            await asyncio.sleep(1.0)
    except Exception as error:
        _raise_worker_http_error(error)


@worker_agent_router.post("/jobs/{job_id}/complete")
async def complete_worker_job(
    job_id: str,
    request: WorkerCompleteRequest,
    worker=Depends(_require_worker_agent),
    service: WorkerControlPlaneService = Depends(get_worker_control_service),
):
    try:
        job = await service.complete_job(
            worker=worker,
            job_id=job_id,
            audio_base64=request.audio_base64,
            content_type=request.content_type,
            source_url=request.source_url,
            result_payload=request.result_payload,
        )
        return {"success": True, "job": job}
    except Exception as error:
        _raise_worker_http_error(error)


@worker_agent_router.post("/jobs/{job_id}/fail")
async def fail_worker_job(
    job_id: str,
    request: WorkerFailRequest,
    worker=Depends(_require_worker_agent),
    service: WorkerControlPlaneService = Depends(get_worker_control_service),
):
    try:
        job = service.fail_job(
            worker=worker,
            job_id=job_id,
            error_code=request.error_code,
            error_message=request.error_message,
            retryable=request.retryable,
        )
        return {"success": True, "job": job}
    except Exception as error:
        _raise_worker_http_error(error)
