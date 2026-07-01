import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from auth.auth import get_current_user
from core.database import get_db
from core.internal_service_auth import build_tts_httpx_client_kwargs
from repositories.user_voice_settings_repository import UserVoiceSettingsRepository
from services.voice_management_upstream import (
    ensure_voice_management_provider,
    provider_admin_api_base,
    provider_request_params,
    raise_upstream_http_error,
    tts_auth_headers,
)
from services.voice_management_service import VoiceManagementService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _tts_auth_headers(provider: str) -> dict:
    return tts_auth_headers(provider)


def _is_admin(user: dict) -> bool:
    return user.get("role") == "admin" or bool(user.get("is_admin", False))


def _require_admin(user: dict) -> None:
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")


def _resolve_provider(provider: Optional[str]) -> str:
    return ensure_voice_management_provider(provider or "f5")


def _provider_base_url(provider: str) -> str:
    return provider_admin_api_base(provider).removesuffix("/api/admin")


def _provider_params(provider: str, extra: Optional[dict] = None) -> dict:
    return provider_request_params(provider, extra)


def _raise_tts_upstream_error(response: httpx.Response, operation: str) -> None:
    if response.status_code == 400:
        detail = "Invalid request to TTS service"
    elif response.status_code == 404:
        detail = "Resource not found in TTS service"
    else:
        detail = "TTS service request failed"
    raise_upstream_http_error(
        response=response,
        operation=operation,
        default_detail=detail,
    )


@router.put("/voices/{voice_id}/settings")
async def update_voice_settings(
    voice_id: int,
    settings_dict: dict = Body(..., embed=False, description="Voice settings"),
    provider: str = "f5",
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update global voice settings in upstream and save personal admin override in bot_service DB."""
    _require_admin(user)

    resolved_provider = _resolve_provider(provider)
    service = VoiceManagementService(db)

    try:
        await service.admin_update_global_voice(
            voice_id=voice_id,
            settings_data=settings_dict,
            provider=resolved_provider,
        )

        # Keep compatibility with historical behavior: persist admin-specific override locally.
        voice_name = str(settings_dict.get("voice_name") or "").strip()
        if not voice_name:
            voice_info = await service.get_voice_info(voice_id, provider=resolved_provider)
            voice_name = str((voice_info or {}).get("name") or "").strip() or f"voice_{voice_id}"

        repository = UserVoiceSettingsRepository(db)
        local_settings = repository.update_or_create_by_voice_id(
            user_id=user["id"],
            voice_id=voice_id,
            settings_data={**settings_dict, "voice_name": voice_name},
            tts_provider=resolved_provider,
        )

        return {
            "status": "success",
            "message": "Voice settings updated",
            "provider": resolved_provider,
            "settings": {
                "voice_id": local_settings.voice_id,
                "cfg_strength": local_settings.cfg_strength,
                "speed_preset": local_settings.speed_preset,
                "volume": local_settings.volume,
            },
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Update voice settings error")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/voices/test")
async def test_voice(
    voice_name: str = Body(...),
    user_id: int = Body(...),
    test_text: str = Body(...),
    cfg_strength: Optional[float] = Body(None),
    speed_preset: Optional[str] = Body(None),
    provider: str = "f5",
    user: dict = Depends(get_current_user),
):
    """Proxy test synthesis to selected provider/gateway."""
    _require_admin(user)

    # Preserve old contract and prevent accidental cross-user testing via this legacy endpoint.
    if user.get("id") != user_id:
        raise HTTPException(status_code=403, detail="User ID mismatch")

    resolved_provider = _resolve_provider(provider)
    upstream_url = _provider_base_url(resolved_provider)

    data = {
        "voice_name": voice_name,
        "user_id": str(user_id),
        "test_text": test_text,
    }
    if cfg_strength is not None:
        data["cfg_strength"] = str(cfg_strength)
    if speed_preset is not None:
        data["speed_preset"] = speed_preset

    try:
        async with httpx.AsyncClient(timeout=30.0, **build_tts_httpx_client_kwargs()) as client:
            response = await client.post(
                f"{upstream_url}/api/admin/voices/test",
                data=data,
                headers=_tts_auth_headers(resolved_provider),
                params=_provider_params(resolved_provider),
            )

        if response.status_code != 200:
            _raise_tts_upstream_error(response, "test voice")

        return response.json()
    except HTTPException:
        raise
    except (httpx.ConnectError, httpx.TimeoutException, httpx.ConnectTimeout) as error:
        logger.warning("TTS service unavailable while testing voice: %s", error)
        raise HTTPException(
            status_code=503,
            detail={
                "error": "tts_service_unavailable",
                "message": "TTS service is unavailable",
                "tts_service_url": upstream_url,
            },
        )
    except Exception:
        logger.exception("Test voice error")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/voices")
async def get_admin_voices(
    provider: str = "f5",
    user: dict = Depends(get_current_user),
):
    """Legacy admin voices endpoint (provider/gateway-aware)."""
    _require_admin(user)

    resolved_provider = _resolve_provider(provider)
    upstream_url = _provider_base_url(resolved_provider)

    try:
        async with httpx.AsyncClient(timeout=10.0, **build_tts_httpx_client_kwargs()) as client:
            response = await client.get(
                f"{upstream_url}/api/admin/voices",
                headers=_tts_auth_headers(resolved_provider),
                params=_provider_params(resolved_provider),
            )

        if response.status_code != 200:
            _raise_tts_upstream_error(response, "list admin voices")

        return response.json()
    except HTTPException:
        raise
    except (httpx.ConnectError, httpx.TimeoutException, httpx.ConnectTimeout) as error:
        logger.warning(
            "TTS service unavailable while listing admin voices (%s): %s.",
            upstream_url,
            error,
        )
        raise HTTPException(
            status_code=503,
            detail={
                "code": "tts_voice_upstream_unreachable",
                "message": "TTS voice service is unavailable",
                "provider": resolved_provider,
                "upstream_url": upstream_url,
            },
        ) from error
    except Exception:
        logger.exception("Get admin voices error")
        raise HTTPException(
            status_code=500,
            detail={
                "code": "tts_voice_admin_list_failed",
                "message": "TTS service connection error",
                "provider": resolved_provider,
                "upstream_url": upstream_url,
            },
        )


@router.post("/voices/upload")
async def upload_voice_proxy(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    provider: str = "f5",
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload global voice through provider/gateway-aware service."""
    from validators.file_validators import ALLOWED_AUDIO_TYPES, validate_file_magic_number, validate_voice_file

    _require_admin(user)

    resolved_provider = _resolve_provider(provider)
    service = VoiceManagementService(db)
    temp_file_path: Optional[str] = None

    try:
        validate_voice_file(file)
        file_content = await file.read()

        import os
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False, suffix=".tmp") as temp_file:
            temp_file.write(file_content)
            temp_file_path = temp_file.name

        is_valid, error = validate_file_magic_number(temp_file_path, ALLOWED_AUDIO_TYPES)
        if not is_valid:
            logger.warning(
                "[BLOCKED] [SECURITY] Admin voice upload rejected - invalid magic number: "
                "admin=%s, filename=%s, error=%s",
                user.get("id"),
                file.filename,
                error,
            )
            raise HTTPException(
                status_code=400,
                detail="Invalid file content. File may be malicious or corrupted.",
            )

        result = await service.admin_upload_voice(
            name=name or "",
            filename=file.filename,
            content=file_content,
            content_type=file.content_type,
            provider=resolved_provider,
        )
        return result
    except HTTPException:
        raise
    except Exception:
        logger.exception("Upload voice error")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        if temp_file_path:
            import os

            if os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except Exception as cleanup_error:  # pragma: no cover
                    logger.warning("Failed to cleanup temp file: %s", cleanup_error)


@router.delete("/voices/{voice_id}")
async def delete_voice_proxy(
    voice_id: int,
    provider: str = "f5",
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete voice in provider/gateway and cleanup local per-user voice overrides."""
    _require_admin(user)

    resolved_provider = _resolve_provider(provider)
    service = VoiceManagementService(db)

    try:
        await service.admin_delete_global_voice(voice_id=voice_id, provider=resolved_provider)
        service.repository.delete_by_voice_id(voice_id=voice_id, tts_provider=resolved_provider)
        return {"success": True, "voice_id": voice_id, "provider": resolved_provider}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Delete voice error")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/voices/{voice_id}/rename")
async def rename_voice_proxy(
    voice_id: int,
    new_name: str = Body(...),
    provider: str = "f5",
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Rename global voice in selected provider/gateway."""
    _require_admin(user)

    resolved_provider = _resolve_provider(provider)
    service = VoiceManagementService(db)

    try:
        await service.admin_rename_global_voice(
            voice_id=voice_id,
            new_name=new_name,
            provider=resolved_provider,
        )
        return {
            "success": True,
            "voice_id": voice_id,
            "new_name": new_name,
            "provider": resolved_provider,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Rename voice error")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/voices/{voice_id}/transcribe")
async def transcribe_voice_proxy(
    voice_id: int,
    provider: str = "f5",
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Transcribe global voice (alias to retranscribe in upstream contract)."""
    _require_admin(user)

    resolved_provider = _resolve_provider(provider)
    service = VoiceManagementService(db)

    try:
        return await service.admin_retranscribe_global_voice(
            voice_id=voice_id,
            provider=resolved_provider,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Transcribe voice error")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/voices/{voice_id}/retranscribe")
async def retranscribe_voice_proxy(
    voice_id: int,
    provider: str = "f5",
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retranscribe global voice in selected provider/gateway."""
    _require_admin(user)

    resolved_provider = _resolve_provider(provider)
    service = VoiceManagementService(db)

    try:
        return await service.admin_retranscribe_global_voice(
            voice_id=voice_id,
            provider=resolved_provider,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Retranscribe voice error")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/voices/{voice_id}/toggle")
async def toggle_voice_proxy(
    voice_id: int,
    provider: str = "f5",
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Toggle voice active status in selected provider/gateway."""
    _require_admin(user)

    resolved_provider = _resolve_provider(provider)
    service = VoiceManagementService(db)

    try:
        return await service.admin_toggle_global_voice(
            voice_id=voice_id,
            provider=resolved_provider,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Toggle voice error")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/tts/stats")
async def get_tts_stats(
    provider: str = "f5",
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get TTS provider/gateway stats for admin panel."""
    _require_admin(user)

    resolved_provider = _resolve_provider(provider)
    service = VoiceManagementService(db)

    try:
        return await service.admin_get_tts_stats(provider=resolved_provider)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Get TTS stats error")
        raise HTTPException(status_code=500, detail="Internal server error")


