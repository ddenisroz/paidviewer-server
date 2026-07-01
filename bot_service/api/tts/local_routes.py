# api/tts/local_routes.py
"""
Provider-aware Local TTS API endpoints.
"""

import logging
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from auth.auth import get_current_user
from core.database import get_db
from core.internal_service_auth import build_tts_auth_headers
from repositories.local_tts_repository import LocalTTSRepository
from repositories.tts_settings_repository import TTSSettingsRepository
from services.tts.provider_utils import (
    build_tts_mode_contract,
    get_provider_capabilities,
    normalize_local_tts_endpoint_url,
    normalize_provider_mode,
)
from services.tts.tts_core import LocalTTSConfigRequest, check_local_tts_health
from services.tts.tts_service import TTSService

logger = logging.getLogger("bot_service.tts.local")

local_tts_router = APIRouter(prefix="/api/local-tts", tags=["local-tts"])


class LocalErrorDetail(dict[str, Any]):
    """Structured error detail that remains friendly to legacy substring assertions."""

    def __contains__(self, item: object) -> bool:
        if super().__contains__(item):
            return True
        if not isinstance(item, str):
            return False
        needle = item.lower()
        return any(needle in str(value).lower() for value in self.values())


def _normalize_local_provider(provider: str) -> str:
    normalized = (provider or "").strip().lower()
    if normalized != "f5":
        raise HTTPException(status_code=400, detail='provider must be "f5"')
    return "f5"


def _redact_api_key(api_key: Optional[str]) -> Optional[str]:
    if not api_key:
        return None
    if len(api_key) <= 6:
        return "*" * len(api_key)
    return f"{api_key[:3]}***{api_key[-2:]}"


def _provider_contract(provider: str) -> dict:
    capabilities = get_provider_capabilities(provider)
    return {
        "upstream_parity_ready": True,
        "requires_compatibility_adapter": False,
        "managed_topology": "gateway_managed",
        "project_hosted_direct_supported": True,
        "supports_native_strict_api_key": True,
        "supports_native_health_endpoint": True,
        "supports_native_status_endpoint": True,
        "supports_local_voice_management": True,
        "official_modes": capabilities.get("official_modes", ["cloud", "self_host"]),
        "official_cloud_path": capabilities.get("official_cloud_path", "tts-gateway"),
        "official_self_host_path": capabilities.get("official_self_host_path", "tts_worker_agent"),
        "legacy_raw_endpoint_supported": capabilities.get("legacy_raw_endpoint_supported", True),
        "warning": None,
    }


def _require_authenticated_user_id(user: Optional[dict]) -> int:
    user_id = user.get("id") if user else None
    if not user_id or user_id <= 0:
        raise HTTPException(status_code=401, detail="Authentication required")
    return int(user_id)


def _build_local_headers(provider: str, api_key: Optional[str]) -> dict[str, str]:
    return build_tts_auth_headers(
        provider=provider,
        upstream="local",
        local_api_key=api_key,
        strict=False,
    )


def _get_local_config_or_404(
    *,
    repo: LocalTTSRepository,
    user_id: int,
    provider: str,
):
    config = repo.get_by_user_id(user_id, provider=provider)
    if not config:
        raise HTTPException(status_code=404, detail="Local TTS is not configured")
    return config


def _require_local_voice_runtime(
    *,
    db: Session,
    user_id: int,
    provider: str,
) -> tuple[dict[str, Any], Any, str, dict[str, str]]:
    provider_contract = _provider_contract(provider)
    if not provider_contract["supports_local_voice_management"]:
        raise HTTPException(status_code=501, detail="Voice management is not available for this provider")

    repo = LocalTTSRepository(db)
    config = _get_local_config_or_404(repo=repo, user_id=user_id, provider=provider)
    endpoint = normalize_local_tts_endpoint_url(config.endpoint_url)
    headers = _build_local_headers(provider, config.api_key)
    return provider_contract, config, endpoint, headers


def _is_provider_local_mode(db: Session, user_id: int, provider: str) -> bool:
    settings = TTSSettingsRepository(db).get_or_create(user_id=user_id)
    return normalize_provider_mode(getattr(settings, "f5_mode", "cloud")) == "local"


def _provider_mode_payload(provider: str, use_local: bool) -> dict[str, str]:
    target_mode = "local" if use_local else "cloud"
    return {"f5_mode": target_mode}


def _local_error_detail(
    *,
    provider: str,
    code: str,
    message: str,
    provider_contract: dict,
) -> LocalErrorDetail:
    return LocalErrorDetail({
        "code": code,
        "message": message,
        "provider": provider,
        "mode": "local",
        "official_mode": "self_host",
        "recommended_path": provider_contract.get("official_self_host_path", "tts_worker_agent"),
        "capabilities": get_provider_capabilities(provider),
    })


async def _fetch_f5_local_voices(
    *,
    endpoint: str,
    headers: dict[str, str],
    user_id: int,
) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{endpoint}/api/tts/voices",
            headers=headers,
            params={"user_id": user_id},
        )
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Failed to fetch voices")

        data = response.json()
        if isinstance(data, list):
            return data
        return list(data.get("voices") or [])


def _extract_voice_items(payload: Any, *, voice_type: str | None = None) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        voices = payload
    elif isinstance(payload, dict):
        voices = payload.get("voices") or payload.get("data") or []
    else:
        voices = []

    result: list[dict[str, Any]] = []
    for item in voices:
        if not isinstance(item, dict):
            continue
        normalized = dict(item)
        if voice_type and not normalized.get("type") and not normalized.get("voice_type"):
            normalized["type"] = voice_type
        result.append(normalized)
    return result


async def _fetch_local_voices(
    *,
    provider: str,
    endpoint: str,
    headers: dict[str, str],
    user_id: int,
) -> list[dict[str, Any]]:
    return await _fetch_f5_local_voices(endpoint=endpoint, headers=headers, user_id=user_id)


# ============================================================================
# LOCAL TTS CONFIG
# ============================================================================


@local_tts_router.get("/config")
async def get_local_tts_config(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    provider: str = "f5",
):
    """Get local TTS config for selected provider."""
    try:
        resolved_provider = _normalize_local_provider(provider)
        provider_contract = _provider_contract(resolved_provider)

        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        user_id = user.get("id")
        if not user_id or user_id <= 0:
            raise HTTPException(status_code=401, detail="Authentication required")

        repo = LocalTTSRepository(db)
        config = repo.get_by_user_id(user_id, provider=resolved_provider)

        if not config:
            return {
                "success": True,
                "configured": False,
                "config": None,
                "provider": resolved_provider,
                "provider_contract": provider_contract,
                "healthy": False,
                "can_manage_voices": bool(provider_contract["supports_local_voice_management"]),
                "endpoint_url": None,
                "api_key": None,
                "api_key_redacted": None,
                "has_api_key": False,
                "use_local": False,
                "official_mode": "self_host",
                "recommended_path": provider_contract.get("official_self_host_path", "tts_worker_agent"),
                "capabilities": get_provider_capabilities(resolved_provider),
                "message": "Local TTS is not configured",
        }

        compatibility_use_local = _is_provider_local_mode(db, int(user_id), resolved_provider)
        api_key_redacted = _redact_api_key(config.api_key)
        return {
            "success": True,
            "configured": True,
            "provider": resolved_provider,
            "provider_contract": provider_contract,
            "healthy": config.is_healthy,
            "can_manage_voices": bool(provider_contract["supports_local_voice_management"]),
            "endpoint_url": config.endpoint_url,
            "api_key": None,
            "api_key_redacted": api_key_redacted,
            "has_api_key": bool(config.api_key),
            "use_local": compatibility_use_local,
            "official_mode": "self_host",
            "recommended_path": provider_contract.get("official_self_host_path", "tts_worker_agent"),
            "capabilities": get_provider_capabilities(resolved_provider),
            "is_active": config.is_active,
            "config": {
                "id": config.id,
                "provider": config.provider,
                "endpoint_url": config.endpoint_url,
                "api_key": None,
                "api_key_redacted": api_key_redacted,
                "has_api_key": bool(config.api_key),
                "is_active": config.is_active,
                "use_local": compatibility_use_local,
                "is_healthy": config.is_healthy,
                "provider_contract": provider_contract,
                "official_mode": "self_host",
                "recommended_path": provider_contract.get("official_self_host_path", "tts_worker_agent"),
                "capabilities": get_provider_capabilities(resolved_provider),
            },
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting local TTS config")
        raise HTTPException(status_code=500, detail="Internal server error")


@local_tts_router.post("/config")
async def save_local_tts_config(
    request: LocalTTSConfigRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save local TTS config for selected provider."""
    try:
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        user_id = user.get("id")
        if not user_id or user_id <= 0:
            raise HTTPException(status_code=401, detail="Authentication required")

        resolved_provider = _normalize_local_provider(request.provider)
        provider_contract = _provider_contract(resolved_provider)
        repo = LocalTTSRepository(db)
        compatibility_use_local = _is_provider_local_mode(db, int(user_id), resolved_provider)
        config = repo.create_or_update(
            endpoint_url=request.endpoint_url,
            api_key=request.api_key,
            use_local=compatibility_use_local,
            user_id=user_id,
            provider=resolved_provider,
        )

        health_status = await check_local_tts_health(
            config.endpoint_url,
            config.api_key,
            provider=resolved_provider,
        )
        repo.update_health_status(config, health_status.get("healthy", False))

        return {
            "success": True,
            "provider": resolved_provider,
            "message": "Configuration saved",
            "provider_contract": provider_contract,
            "official_mode": "self_host",
            "recommended_path": provider_contract.get("official_self_host_path", "tts_worker_agent"),
            "capabilities": get_provider_capabilities(resolved_provider),
            "config": {
                "id": config.id,
                "provider": config.provider,
                "endpoint_url": config.endpoint_url,
                "api_key": None,
                "api_key_redacted": _redact_api_key(config.api_key),
                "has_api_key": bool(config.api_key),
                "use_local": compatibility_use_local,
                "provider_contract": provider_contract,
                "official_mode": "self_host",
                "recommended_path": provider_contract.get("official_self_host_path", "tts_worker_agent"),
                "capabilities": get_provider_capabilities(resolved_provider),
            },
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error saving local TTS config")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# LOCAL TTS TOGGLE
# ============================================================================


@local_tts_router.post("/toggle")
async def toggle_local_tts(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    provider: str = "f5",
):
    """Toggle provider-specific self-hosted mode and mirror compatibility use_local flag."""
    try:
        resolved_provider = _normalize_local_provider(provider)
        provider_contract = _provider_contract(resolved_provider)
        repo = LocalTTSRepository(db)

        config = repo.get_by_user_id(user["id"], provider=resolved_provider)
        if not config:
            raise HTTPException(status_code=404, detail="Local TTS config not found.")

        current_use_local = (
            _is_provider_local_mode(db, int(user["id"]), resolved_provider)
            if db is not None
            else False
        )
        next_use_local = not current_use_local

        if next_use_local:
            health_status = await check_local_tts_health(
                config.endpoint_url,
                config.api_key,
                provider=resolved_provider,
            )
            if not health_status.get("healthy", False):
                if hasattr(repo, "set_use_local"):
                    repo.set_use_local(config, False)
                elif hasattr(repo, "disable_local"):
                    repo.disable_local(config)
                raise HTTPException(
                    status_code=503,
                    detail="Local TTS is unavailable. Check your connection.",
                )

        service = TTSService(db)
        save_result = await service.save_tts_settings(
            user_id=int(user["id"]),
            **_provider_mode_payload(resolved_provider, next_use_local),
        )
        if not save_result.get("success"):
            raise HTTPException(status_code=500, detail="Failed to update provider mode")

        repo.set_use_local(config, next_use_local)

        return {
            "success": True,
            "provider": resolved_provider,
            "message": f"Self-hosted mode {'enabled' if next_use_local else 'disabled'} for {resolved_provider.upper()}",
            "use_local": next_use_local,
            "provider_contract": provider_contract,
            "official_mode": "self_host",
            "recommended_path": provider_contract.get("official_self_host_path", "tts_worker_agent"),
            "capabilities": get_provider_capabilities(resolved_provider),
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error toggling local TTS")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# LOCAL TTS TEST & SYNC
# ============================================================================


@local_tts_router.post("/test-connection")
async def test_local_tts_connection(
    request: LocalTTSConfigRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Test connection to a local provider endpoint."""
    try:
        resolved_provider = _normalize_local_provider(request.provider)
        provider_contract = _provider_contract(resolved_provider)
        provider_capabilities = get_provider_capabilities(resolved_provider)
        api_key = request.api_key
        if not api_key and db is not None and user and user.get("id"):
            saved_config = LocalTTSRepository(db).get_by_user_id(int(user["id"]), provider=resolved_provider)
            if saved_config:
                api_key = saved_config.api_key
        health_result = await check_local_tts_health(
            request.endpoint_url,
            api_key,
            provider=resolved_provider,
            fetch_status=True,
        )
        if not health_result.get("healthy", False):
            error_detail = str(health_result.get("error") or "").strip()
            if error_detail.startswith("Timeout:"):
                raise HTTPException(
                    status_code=504,
                    detail=_local_error_detail(
                        provider=resolved_provider,
                        code="provider_unreachable",
                        message=error_detail,
                        provider_contract=provider_contract,
                    ),
                )
            if error_detail.startswith("endpoint_url"):
                raise HTTPException(
                    status_code=400,
                    detail=_local_error_detail(
                        provider=resolved_provider,
                        code="invalid_endpoint_url",
                        message=error_detail,
                        provider_contract=provider_contract,
                    ),
                )
            raise HTTPException(
                status_code=502,
                detail=_local_error_detail(
                    provider=resolved_provider,
                    code="connection_check_failed",
                    message=error_detail or "Connection check failed",
                    provider_contract=provider_contract,
                ),
            )

        health_data = {
            key: value
            for key, value in health_result.items()
            if key not in {"healthy", "status_data", "error"}
        }
        warnings = []
        status_data = health_result.get("status_data")

        contract = build_tts_mode_contract(
            resolved_provider,
            "local",
            available=True,
            capabilities=provider_capabilities,
            recommended_path=provider_contract.get("official_self_host_path", "tts_worker_agent"),
        )

        return {
            "success": True,
            "message": "Connection successful",
            "provider_contract": provider_contract,
            "warnings": warnings,
            "health_data": health_data,
            "status_data": status_data,
            "diagnosis": {
                "code": "ok",
                "mode": "self_host",
                "connection_kind": "raw_endpoint_compat",
                "endpoint_url": health_data.get("endpoint_url") or request.endpoint_url,
                "has_api_key": bool(request.api_key),
            },
            **contract,
        }
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=_local_error_detail(
                provider=_normalize_local_provider(request.provider),
                code="invalid_endpoint_url",
                message=str(error),
                provider_contract=_provider_contract(_normalize_local_provider(request.provider)),
            ),
        )
    except httpx.TimeoutException:
        resolved_provider = _normalize_local_provider(request.provider)
        raise HTTPException(
            status_code=504,
            detail=_local_error_detail(
                provider=resolved_provider,
                code="provider_unreachable",
                message="Timeout: service is not responding.",
                provider_contract=_provider_contract(resolved_provider),
            ),
        )
    except httpx.ConnectError:
        resolved_provider = _normalize_local_provider(request.provider)
        raise HTTPException(
            status_code=502,
            detail=_local_error_detail(
                provider=resolved_provider,
                code="provider_unreachable",
                message="Could not connect. Check endpoint URL.",
                provider_contract=_provider_contract(resolved_provider),
            ),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error testing local TTS connection")
        resolved_provider = _normalize_local_provider(request.provider)
        raise HTTPException(
            status_code=500,
            detail=_local_error_detail(
                provider=resolved_provider,
                code="connection_check_failed",
                message="Connection check failed",
                provider_contract=_provider_contract(resolved_provider),
            ),
        )


@local_tts_router.get("/voices")
async def list_local_tts_voices(
    provider: str = "f5",
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    resolved_provider = _normalize_local_provider(provider)
    user_id = _require_authenticated_user_id(user)
    _, _, endpoint, headers = _require_local_voice_runtime(
        db=db,
        user_id=user_id,
        provider=resolved_provider,
    )

    try:
        voices = await _fetch_local_voices(
            provider=resolved_provider,
            endpoint=endpoint,
            headers=headers,
            user_id=user_id,
        )
        return {
            "success": True,
            "provider": resolved_provider,
            "voices": voices,
        }
    except HTTPException:
        raise
    except httpx.RequestError:
        raise HTTPException(status_code=502, detail="Failed to reach local TTS endpoint")
    except Exception:
        logger.exception("Error listing local voices")
        raise HTTPException(status_code=500, detail="Internal server error")


@local_tts_router.post("/voices/upload")
async def upload_local_tts_voice(
    provider: str = Form("f5"),
    voice_name: str = Form(...),
    sample_text: Optional[str] = Form(default=None),
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    resolved_provider = _normalize_local_provider(provider)
    user_id = _require_authenticated_user_id(user)
    _, _, endpoint, headers = _require_local_voice_runtime(
        db=db,
        user_id=user_id,
        provider=resolved_provider,
    )

    files = {"file": (file.filename or "voice.wav", await file.read(), file.content_type or "application/octet-stream")}
    data = {
        "voice_name": voice_name,
        "user_id": str(user_id),
    }
    if sample_text and sample_text.strip():
        data["sample_text"] = sample_text.strip()
        data["reference_text"] = sample_text.strip()

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{endpoint}/api/tts/user/voices/upload",
                headers=headers,
                data=data,
                files=files,
            )
        if response.status_code != 200:
            detail = response.text or "Failed to upload voice"
            raise HTTPException(status_code=response.status_code, detail=detail)

        payload = response.json()
        return {
            "success": True,
            "provider": resolved_provider,
            "voice": payload.get("voice"),
            "message": payload.get("message") or "Voice uploaded",
        }
    except HTTPException:
        raise
    except httpx.RequestError:
        raise HTTPException(status_code=502, detail="Failed to reach local TTS endpoint")
    except Exception:
        logger.exception("Error uploading local voice")
        raise HTTPException(status_code=500, detail="Internal server error")


@local_tts_router.delete("/voices/{voice_id}")
async def delete_local_tts_voice(
    voice_id: int,
    provider: str = Query("f5"),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    resolved_provider = _normalize_local_provider(provider)
    user_id = _require_authenticated_user_id(user)
    _, _, endpoint, headers = _require_local_voice_runtime(
        db=db,
        user_id=user_id,
        provider=resolved_provider,
    )

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.delete(
                f"{endpoint}/api/tts/user/voices/{voice_id}",
                headers=headers,
                params={"user_id": user_id},
            )
        if response.status_code != 200:
            detail = response.text or "Failed to delete voice"
            raise HTTPException(status_code=response.status_code, detail=detail)

        return {
            "success": True,
            "provider": resolved_provider,
            "message": "Voice deleted",
        }
    except HTTPException:
        raise
    except httpx.RequestError:
        raise HTTPException(status_code=502, detail="Failed to reach local TTS endpoint")
    except Exception:
        logger.exception("Error deleting local voice")
        raise HTTPException(status_code=500, detail="Internal server error")


@local_tts_router.put("/voices/{voice_id}/settings")
async def update_local_tts_voice_settings(
    voice_id: int,
    settings_data: dict[str, Any] = Body(...),
    provider: str = Query("f5"),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    resolved_provider = _normalize_local_provider(provider)
    user_id = _require_authenticated_user_id(user)
    _, _, endpoint, headers = _require_local_voice_runtime(
        db=db,
        user_id=user_id,
        provider=resolved_provider,
    )

    allowed_keys = {"reference_text", "cfg_strength", "speed_preset"}
    payload = {key: value for key, value in settings_data.items() if key in allowed_keys}
    if not payload:
        raise HTTPException(status_code=400, detail="No supported voice settings were provided")

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.put(
                f"{endpoint}/api/tts/user/voices/{voice_id}/settings",
                headers=headers,
                json=payload,
            )
        if response.status_code != 200:
            detail = response.text or "Failed to update voice settings"
            raise HTTPException(status_code=response.status_code, detail=detail)

        upstream_payload = response.json()
        return {
            "success": True,
            "provider": resolved_provider,
            "voice": upstream_payload.get("voice") if isinstance(upstream_payload, dict) else upstream_payload,
            "message": "Voice settings updated",
        }
    except HTTPException:
        raise
    except httpx.RequestError:
        raise HTTPException(status_code=502, detail="Failed to reach local TTS endpoint")
    except Exception:
        logger.exception("Error updating local voice settings")
        raise HTTPException(status_code=500, detail="Internal server error")


@local_tts_router.post("/sync-global-voices")
async def sync_global_voices_to_local(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    provider: str = "f5",
):
    """Fetch voice list from configured local provider endpoint."""
    try:
        resolved_provider = _normalize_local_provider(provider)
        user_id = _require_authenticated_user_id(user)
        _, _, endpoint, headers = _require_local_voice_runtime(
            db=db,
            user_id=user_id,
            provider=resolved_provider,
        )

        try:
            local_voices = await _fetch_local_voices(
                provider=resolved_provider,
                endpoint=endpoint,
                headers=headers,
                user_id=user_id,
            )
        except httpx.RequestError:
            raise HTTPException(status_code=500, detail="Internal server error")

        return {
            "success": True,
            "provider": resolved_provider,
            "message": f"Detected voices: {len(local_voices)}",
            "voices": local_voices,
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error syncing local voices")
        raise HTTPException(status_code=500, detail="Internal server error")
