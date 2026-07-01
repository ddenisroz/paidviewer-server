# bot_service/api/tts/settings_routes.py
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import logging
import httpx
from pathlib import Path
from typing import List, Optional

from core.database import get_db
from auth.auth import get_current_user
from core.config import settings
from core.internal_service_auth import TTSAuthConfigError, build_tts_auth_headers, build_tts_httpx_client_kwargs
from repositories.local_tts_repository import LocalTTSRepository
from services.voice_management_upstream import provider_admin_api_base
from services.tts.tts_service import TTSService
from services.tts.google_cloud_tts import (
    get_google_cloud_tts,
    is_gemini_or_chirp_voice,
    normalize_gcloud_mood,
)
from services.tts.provider_utils import (
    build_tts_mode_contract,
    ProviderRoutingError,
    get_provider_capabilities,
    get_synthesis_upstream_url,
    get_voice_management_upstream_params,
    infer_provider_from_engine,
    normalize_local_tts_endpoint_url,
    normalize_provider,
    normalize_provider_mode,
    should_route_provider_via_gateway,
)
from services.tts.tts_manager import get_tts_manager
from services.tts.tts_core import (
    AudioSettingsRequest,
    TtsSettingsRequest,
    BlockUserRequest, 
    UnblockUserRequest,
    AddWordRequest,
    PlatformSettingsRequest
)

# Prefix is defined in main.py via include_router or here. 
# We decided to use api/tts/__init__.py to include this router.
# Let's define the prefix here to be safe and consistent with synthesis_routes
router = APIRouter(prefix="/api/tts", tags=["tts-settings"])
logger = logging.getLogger(__name__)


class EngineRequest(BaseModel):
    engine_type: str = Field(..., min_length=2, max_length=32)


class GcloudVoiceSelectionRequest(BaseModel):
    voices: List[str] = Field(default_factory=list)


class GcloudVoicePreviewRequest(BaseModel):
    voice_name: str = Field(..., min_length=2, max_length=120)
    text: Optional[str] = Field(default="Hello! This is a Google Cloud voice preview.")
    mood: Optional[str] = Field(default=None, max_length=20)
    model_name: Optional[str] = Field(default=None, max_length=120)

def get_tts_service(db: Session = Depends(get_db)) -> TTSService:
    return TTSService(db)


def _tts_auth_headers(
    provider: str,
    *,
    upstream: str = "voice",
    use_gateway: Optional[bool] = None,
    strict: bool = True,
) -> dict:
    try:
        return build_tts_auth_headers(
            provider=provider,
            upstream=upstream,  # type: ignore[arg-type]
            use_gateway=use_gateway,
            strict=strict,
        )
    except TTSAuthConfigError as error:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "tts_upstream_auth_not_configured",
                "message": str(error),
            },
        ) from error


def _is_admin(user: dict) -> bool:
    return user.get("role") == "admin" or bool(user.get("is_admin", False))


def _normalize_voice_provider(provider: str) -> str:
    normalized_provider = normalize_provider(provider)
    if normalized_provider == "gcloud":
        raise HTTPException(
            status_code=400,
            detail={
                "code": "gcloud_voice_management_not_supported",
                "message": "Google Cloud provider does not support voice CRUD in bot_service.",
            },
        )
    return "f5"


def _voice_management_base_url(provider: str) -> str:
    return provider_admin_api_base(_normalize_voice_provider(provider)).removesuffix("/api/admin")


async def _resolve_user_whitelist_state(*, user_id: int, db: Session) -> bool:
    try:
        snapshot = await TTSService(db).get_tts_status(user_id=user_id)
        return bool(snapshot.get("is_whitelisted"))
    except Exception:
        logger.exception("Failed to resolve user whitelist state user_id=%s", user_id)
        return False


_CANONICAL_ENGINE_TYPES = {
    "gtts",
    "gcloud",
    "f5_cloud",
    "f5_local",
}

_ENGINE_TYPE_ALIASES = {
    "cloud": "f5_cloud",
    "local": "f5_local",
    "f5": "f5_cloud",
}


def _normalize_engine_type(engine_type: str) -> str:
    normalized = (engine_type or "").strip().lower()
    return _ENGINE_TYPE_ALIASES.get(normalized, normalized)


async def _resolve_voice_proxy_provider(
    *,
    requested_provider: Optional[str],
    user_id: int,
    service: TTSService,
) -> str:
    if requested_provider and requested_provider.strip():
        return normalize_provider(requested_provider)

    if not hasattr(service, "get_tts_settings"):
        return "f5"

    try:
        settings_dict = await service.get_tts_settings(user_id=user_id)
        return infer_provider_from_engine(
            settings_dict.get("engine"),
            advanced_provider=settings_dict.get("advanced_provider"),
        )
    except Exception:
        logger.exception("Failed to resolve provider for voice proxy user_id=%s", user_id)
        return "f5"


def _engine_type_to_settings_payload(engine_type: str) -> dict:
    if engine_type == "gtts":
        return {
            "engine": "gtts",
            "use_local_tts": False,
        }
    if engine_type == "gcloud":
        return {
            "engine": "gcloud",
            "advanced_provider": "gcloud",
            "use_local_tts": False,
        }
    if engine_type == "f5_cloud":
        return {
            "engine": "f5tts",
            "advanced_provider": "f5",
            "f5_mode": "cloud",
            "use_local_tts": False,
        }
    if engine_type == "f5_local":
        return {
            "engine": "f5tts",
            "advanced_provider": "f5",
            "f5_mode": "local",
            "use_local_tts": True,
        }
    raise ValueError(f"Unsupported engine_type: {engine_type}")

# ============================================================================
# TTS SETTINGS
# ============================================================================

@router.get("/settings")
async def get_tts_settings(
    user: dict = Depends(get_current_user), 
    service: TTSService = Depends(get_tts_service)
):
    """Get TTS settings for current user."""
    settings_dict = await service.get_tts_settings(user_id=user['id'])
    return settings_dict

@router.post("/settings")
async def update_tts_settings(
    settings_req: TtsSettingsRequest,
    user: dict = Depends(get_current_user),
    service: TTSService = Depends(get_tts_service)
):
    """Update TTS settings."""
    save_payload = {"user_id": user["id"]}
    field_map = {
        "enable7TV": "enable_7tv",
        "enableTwitch": "enable_twitch",
        "enableLexiconFilter": "enable_lexicon_filter",
        "enableCustomLexicon": "enable_custom_lexicon",
        "engine": "engine",
        "advancedProvider": "advanced_provider",
        "f5Mode": "f5_mode",
        "voice": "voice",
        "listeningMode": "listening_mode",
        "maxMessageLength": "max_message_length",
        "skipCommands": "skip_commands",
        "useLocalTTS": "use_local_tts",
        "filterReplies": "filter_replies",
        "filterMentions": "filter_mentions",
        "filterBanwords": "filter_banwords",
        "disableVoiceSelection": "disable_voice_selection",
        "speakSenderName": "speak_sender_name",
        "gcloudVoices": "gcloud_voices",
        "gcloudMood": "gcloud_mood",
    }

    model_fields_set = getattr(settings_req, "model_fields_set", set())
    for request_field, payload_field in field_map.items():
        if request_field not in model_fields_set:
            continue
        value = getattr(settings_req, request_field, None)
        if value is None and request_field in {"gcloudVoices", "gcloudMood"}:
            continue
        if request_field == "maxMessageLength":
            try:
                value = max(50, min(250, int(value)))
            except (TypeError, ValueError):
                value = 150
        save_payload[payload_field] = value

    if "version" in model_fields_set:
        save_payload["client_version"] = settings_req.version

    if len(save_payload) == 1:
        return {"success": True, "message": "No changes provided"}

    result = await service.save_tts_settings(**save_payload)
    if not result.get("success"):
        if result.get("error") == "Version conflict":
             raise HTTPException(status_code=409, detail=result)
        raise HTTPException(status_code=500, detail="Internal server error")

    return result

# ============================================================================
# STATUS & CONTROL
# ============================================================================

@router.get("/status")
async def get_tts_status(
    user: dict = Depends(get_current_user),
    service: TTSService = Depends(get_tts_service)
):
    """Get TTS Status (enabled/disabled)."""
    result = await service.get_tts_status(user_id=user['id'])
    if result.get('error'):
        raise HTTPException(status_code=404, detail="TTS status not found")
    return result


@router.get("/health")
async def get_tts_upstream_health(
    provider: str = "f5",
    mode: str | None = None,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Provider-aware health check routed through bot_service."""
    normalized_provider = normalize_provider(provider)
    normalized_mode = normalize_provider_mode(mode)
    is_whitelisted = await _resolve_user_whitelist_state(user_id=int(user["id"]), db=db)
    provider_capabilities = get_provider_capabilities(normalized_provider)

    def _attach_detail(payload: dict, *, fallback_message: str | None = None) -> dict:
        if payload.get("available"):
            return payload
        detail_message = payload.get("degraded_reason") or fallback_message or "TTS provider is unavailable."
        payload["detail"] = {
            "code": payload.get("error_code"),
            "message": detail_message,
        }
        return payload

    if normalized_provider == "gcloud":
        gcloud = get_google_cloud_tts()
        gcloud_result = await gcloud.list_voices(language_code="ru-RU")
        is_healthy = bool(gcloud_result.get("success"))
        response_payload = build_tts_mode_contract(
            "gcloud",
            "cloud",
            available=is_healthy,
            is_whitelisted=is_whitelisted,
            degraded_reason=None if is_healthy else (gcloud_result.get("error") or "Google Cloud TTS is unavailable."),
            error_code=None if is_healthy else "gcloud_unhealthy",
            capabilities=provider_capabilities,
        )
        response_payload = {
            "success": True,
            "auth_mode": gcloud_result.get("auth_mode"),
            "cached": bool(gcloud_result.get("cached", False)),
            **response_payload,
        }
        if not is_healthy:
            response_payload = _attach_detail(
                response_payload,
                fallback_message=gcloud_result.get("hint"),
            )
            response_payload["detail"]["hint"] = gcloud_result.get("hint")
            response_payload["detail"]["status_code"] = gcloud_result.get("status_code")
        return response_payload

    manager = get_tts_manager()
    local_endpoint_url = None
    local_api_key = None
    use_gateway = should_route_provider_via_gateway(normalized_provider)

    if normalized_mode != "local" and normalized_provider == "f5":
        try:
            from services.worker_control.service import WorkerControlPlaneService

            managed_worker = None
            if settings.worker_control_managed_enabled:
                managed_worker = WorkerControlPlaneService(db).get_preferred_worker(
                    provider=normalized_provider,
                    managed_only=True,
                )
            if managed_worker:
                payload = build_tts_mode_contract(
                    normalized_provider,
                    normalized_mode,
                    available=True,
                    is_whitelisted=is_whitelisted,
                    capabilities=provider_capabilities,
                    upstream={
                        "url": None,
                        "via": "internal-managed-worker",
                        "worker_key": managed_worker.worker_key,
                        "worker_label": managed_worker.label,
                        "managed": True,
                    },
                )
                return {
                    "success": True,
                    **payload,
                }
        except Exception:
            logger.exception("Failed to resolve managed worker-agent health provider=%s", normalized_provider)

    if normalized_mode == "local":
        repo = LocalTTSRepository(db)
        local_config = repo.get_by_user_id(int(user["id"]), provider=normalized_provider)
        worker = None
        try:
            from services.worker_control.service import WorkerControlPlaneService

            if settings.worker_control_self_host_enabled:
                worker = WorkerControlPlaneService(db).get_preferred_worker(
                    provider=normalized_provider,
                    owner_user_id=int(user["id"]),
                    managed_only=False,
                )
        except Exception:
            logger.exception("Failed to resolve worker-agent local health provider=%s", normalized_provider)

        if not local_config or not str(local_config.endpoint_url or "").strip():
            if worker:
                payload = build_tts_mode_contract(
                    normalized_provider,
                    "local",
                    available=True,
                    is_whitelisted=is_whitelisted,
                    capabilities=provider_capabilities,
                    recommended_path="tts_worker_agent",
                    upstream={
                        "url": None,
                        "via": "worker-agent",
                        "worker_key": worker.worker_key,
                        "worker_label": worker.label,
                    },
                )
                return {
                    "success": True,
                    **payload,
                }
            payload = build_tts_mode_contract(
                normalized_provider,
                "local",
                available=False,
                is_whitelisted=is_whitelisted,
                degraded_reason=f"Self-hosted {normalized_provider.upper()} endpoint is not configured.",
                error_code="local_tts_not_configured",
                capabilities=provider_capabilities,
                recommended_path="tts_worker_agent",
            )
            return _attach_detail({
                "success": True,
                **payload,
            })
        try:
            local_endpoint_url = normalize_local_tts_endpoint_url(local_config.endpoint_url)
        except ValueError as error:
            if worker:
                payload = build_tts_mode_contract(
                    normalized_provider,
                    "local",
                    available=True,
                    is_whitelisted=is_whitelisted,
                    capabilities=provider_capabilities,
                    recommended_path="tts_worker_agent",
                    upstream={
                        "url": None,
                        "via": "worker-agent",
                        "worker_key": worker.worker_key,
                        "worker_label": worker.label,
                    },
                )
                return {
                    "success": True,
                    **payload,
                }
            payload = build_tts_mode_contract(
                normalized_provider,
                "local",
                available=False,
                is_whitelisted=is_whitelisted,
                degraded_reason=str(error),
                error_code="local_tts_invalid_endpoint",
                capabilities=provider_capabilities,
                recommended_path="tts_worker_agent",
            )
            return _attach_detail({
                "success": True,
                **payload,
            })
        local_api_key = str(local_config.api_key or "").strip() or None
        use_gateway = False

    try:
        synthesis_url = (
            local_endpoint_url
            if local_endpoint_url
            else get_synthesis_upstream_url(normalized_provider).rstrip("/")
        )
    except ProviderRoutingError as error:
        raise HTTPException(status_code=400, detail={"code": str(error), "message": str(error)}) from error

    if not local_endpoint_url:
        _tts_auth_headers(
            normalized_provider,
            upstream="synthesis",
            use_gateway=use_gateway,
        )

    is_healthy = await manager.check_tts_service_health(
        force_check=True,
        provider=normalized_provider,
        endpoint_override=local_endpoint_url,
        endpoint_api_key=local_api_key,
    )
    if normalized_mode == "local" and not is_healthy:
        try:
            from services.worker_control.service import WorkerControlPlaneService

            worker = None
            if settings.worker_control_self_host_enabled:
                worker = WorkerControlPlaneService(db).get_preferred_worker(
                    provider=normalized_provider,
                    owner_user_id=int(user["id"]),
                    managed_only=False,
                )
            if worker:
                payload = build_tts_mode_contract(
                    normalized_provider,
                    "local",
                    available=True,
                    is_whitelisted=is_whitelisted,
                    capabilities=provider_capabilities,
                    recommended_path="tts_worker_agent",
                    upstream={
                        "url": None,
                        "via": "worker-agent",
                        "worker_key": worker.worker_key,
                        "worker_label": worker.label,
                    },
                )
                return {
                    "success": True,
                    **payload,
                }
        except Exception:
            logger.exception("Failed to resolve local worker-agent fallback provider=%s", normalized_provider)
    payload = build_tts_mode_contract(
        normalized_provider,
        normalized_mode,
        available=bool(is_healthy),
        is_whitelisted=is_whitelisted,
        degraded_reason=None if is_healthy else f"{normalized_provider.upper()} runtime did not respond to health checks.",
        error_code=None if is_healthy else "tts_upstream_unhealthy",
        capabilities=provider_capabilities,
        upstream={
            "url": synthesis_url,
            "via": "local" if local_endpoint_url else ("gateway" if use_gateway else "direct"),
        },
    )
    response_payload = {
        "success": True,
        **payload,
    }
    if not is_healthy:
        response_payload = _attach_detail(response_payload)
    return response_payload


@router.post("/engine")
async def set_tts_engine(
    request: EngineRequest,
    user: dict = Depends(get_current_user),
    service: TTSService = Depends(get_tts_service)
):
    """
    Set TTS engine type.

    Canonical values:
    - gtts
    - gcloud
    - f5_cloud / f5_local

    Backward-compatible aliases are accepted:
    - cloud -> f5_cloud
    - local -> f5_local
    """
    raw_engine_type = request.engine_type
    engine_type = _normalize_engine_type(raw_engine_type)
    if engine_type not in _CANONICAL_ENGINE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid engine. Must be one of: {sorted(_CANONICAL_ENGINE_TYPES)}",
        )

    payload = _engine_type_to_settings_payload(engine_type)
    result = await service.save_tts_settings(user_id=user['id'], **payload)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail="Failed to update engine")

    return {"success": True, "engine_type": engine_type}

@router.post("/enable")
async def enable_tts(
    user: dict = Depends(get_current_user),
    service: TTSService = Depends(get_tts_service)
):
    """Enable TTS."""
    success = await service.enable_tts(user_id=user['id'])
    return {"success": success}

@router.post("/disable")
async def disable_tts(
    user: dict = Depends(get_current_user),
    service: TTSService = Depends(get_tts_service)
):
    """Disable TTS."""
    success = await service.disable_tts(user_id=user['id'])
    return {"success": success}

# ============================================================================
# AUDIO SETTINGS
# ============================================================================

@router.get("/audio-settings")
async def get_audio_settings(
    user: dict = Depends(get_current_user),
    service: TTSService = Depends(get_tts_service)
):
    """Get audio settings."""
    return await service.get_audio_settings(user_id=user['id'])

@router.post("/audio-settings")
async def update_audio_settings(
    settings_req: AudioSettingsRequest,
    user: dict = Depends(get_current_user),
    service: TTSService = Depends(get_tts_service)
):
    """Update audio settings."""
    success = await service.save_audio_settings(
        user_id=user['id'],
        website_volume=settings_req.websiteVolume,
        obs_volume=settings_req.obsVolume,
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save audio settings")
    updated = await service.get_audio_settings(user_id=user["id"])
    return {"success": True, "data": updated, **updated}

# ============================================================================
# FILTERS
# ============================================================================

@router.get("/filters/words")
async def get_filtered_words(
    user: dict = Depends(get_current_user),
    service: TTSService = Depends(get_tts_service)
):
    """Get filtered words."""
    return await service.get_filtered_words(user_id=user['id'])

@router.post("/filters/words")
async def add_filtered_word(
    request: AddWordRequest,
    user: dict = Depends(get_current_user),
    service: TTSService = Depends(get_tts_service)
):
    """Add word to filter."""
    success = await service.add_filtered_word(user['id'], request.word, request.platform)
    if not success:
        raise HTTPException(status_code=409, detail="Word already exists or could not be added")
    return {"success": True}

@router.delete("/filters/words/{word_id}")
async def remove_filtered_word(
    word_id: int,
    user: dict = Depends(get_current_user),
    service: TTSService = Depends(get_tts_service)
):
    """Remove word from filter."""
    success = await service.remove_filtered_word(user['id'], word_id)
    if not success:
        raise HTTPException(status_code=404, detail="Word not found")
    return {"success": True}

# ============================================================================
# BLOCKED USERS
# ============================================================================

@router.get("/blocked-users")
async def get_blocked_users(
    user: dict = Depends(get_current_user),
    service: TTSService = Depends(get_tts_service)
):
    """Get blocked users."""
    return await service.get_blocked_users(user_id=user['id'])

@router.post("/blocked-users")
async def block_user(
    request: BlockUserRequest,
    user: dict = Depends(get_current_user),
    service: TTSService = Depends(get_tts_service)
):
    """Block user."""
    channel_name = request.channel_name or (
        (user.get('twitch_username') if request.platform == 'twitch' else user.get('vk_username') or user.get('vk_channel_name'))
        or user.get('username')
    )
    if not channel_name:
        raise HTTPException(status_code=400, detail="Failed to resolve channel_name")

    success = await service.block_user(
        user_id=user['id'], channel_name=channel_name, platform=request.platform, username=request.username
    )
    if not success:
        return {"success": True, "message": "User already blocked", "already_blocked": True}
    return {"success": True}

@router.post("/blocked-users/unblock")
async def unblock_user(
    request: UnblockUserRequest,
    user: dict = Depends(get_current_user),
    service: TTSService = Depends(get_tts_service)
):
    """Unblock user."""
    channel_name = request.channel_name or (
        (user.get('twitch_username') if request.platform == 'twitch' else user.get('vk_username') or user.get('vk_channel_name'))
        or user.get('username')
    )
    if not channel_name:
        raise HTTPException(status_code=400, detail="Failed to resolve channel_name")

    success = await service.unblock_user(
         user_id=user['id'], channel_name=channel_name, platform=request.platform, username=request.username
    )
    if not success:
         raise HTTPException(status_code=404, detail="User not found in blacklist")
    return {"success": True}

# ============================================================================
# VOICES (Proxy)
# ============================================================================

@router.get("/voices/global")
async def get_global_voices(
    provider: Optional[str] = None,
    user: dict = Depends(get_current_user),
    service: TTSService = Depends(get_tts_service),
):
    """Get global voices (Proxy)."""
    actor_id = user.get("id", user.get("user_id"))
    if not isinstance(actor_id, int) or actor_id <= 0:
        raise HTTPException(status_code=401, detail="Authentication required")

    resolved_provider = await _resolve_voice_proxy_provider(
        requested_provider=provider,
        user_id=actor_id,
        service=service,
    )
    if resolved_provider == "gcloud":
        return {"voices": [], "provider": "gcloud", "hint": "Use /api/tts/gcloud/voices"}

    tts_url = _voice_management_base_url(resolved_provider)
    try:
        async with httpx.AsyncClient(timeout=10.0, **build_tts_httpx_client_kwargs()) as client:
            resp = await client.get(
                f"{tts_url}/api/tts/voices/global",
                headers=_tts_auth_headers(resolved_provider, upstream="voice", strict=False),
                params=get_voice_management_upstream_params(resolved_provider),
            )
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404:
                return {"voices": []}
            raise HTTPException(status_code=resp.status_code, detail="Failed to fetch provider voices")
    except HTTPException:
        raise
    except httpx.TimeoutException:
        logger.warning("Timeout fetching global voices from TTS service")
        raise HTTPException(status_code=504, detail="TTS service timeout")
    except httpx.RequestError:
        logger.exception("Upstream error fetching global voices")
        raise HTTPException(status_code=502, detail="TTS service unavailable")
    except Exception:
        logger.exception("Error fetching global voices")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/user/voices/{target_user_id}")
async def get_user_voices(
    target_user_id: int,
    provider: Optional[str] = None,
    user: dict = Depends(get_current_user),
    service: TTSService = Depends(get_tts_service),
):
    """Get user voices (Proxy)."""
    actor_id = user.get("id", user.get("user_id"))
    if actor_id != target_user_id and not _is_admin(user):
        raise HTTPException(status_code=403, detail="Access denied")

    resolved_provider = await _resolve_voice_proxy_provider(
        requested_provider=provider,
        user_id=target_user_id,
        service=service,
    )
    if resolved_provider == "gcloud":
        return {"voices": [], "provider": "gcloud", "hint": "Use /api/tts/gcloud/voices"}

    tts_url = _voice_management_base_url(resolved_provider)
    try:
        async with httpx.AsyncClient(timeout=10.0, **build_tts_httpx_client_kwargs()) as client:
            resp = await client.get(
                f"{tts_url}/api/tts/user/voices/{target_user_id}",
                headers=_tts_auth_headers(resolved_provider, upstream="voice", strict=False),
                params=get_voice_management_upstream_params(resolved_provider),
            )
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404:
                return {"voices": []}
            raise HTTPException(status_code=resp.status_code, detail="Failed to fetch user voices")
    except HTTPException:
        raise
    except httpx.TimeoutException:
        logger.warning("Timeout fetching user voices from TTS service for user_id=%s", target_user_id)
        raise HTTPException(status_code=504, detail="TTS service timeout")
    except httpx.RequestError:
        logger.exception("Upstream error fetching user voices for user_id=%s", target_user_id)
        raise HTTPException(status_code=502, detail="TTS service unavailable")
    except Exception:
        logger.exception("Error fetching user voices")
        raise HTTPException(status_code=500, detail="Internal server error")

# ============================================================================
# GOOGLE CLOUD TTS VOICES
# ============================================================================

@router.get("/gcloud/voices")
async def get_gcloud_voices(
    language: Optional[str] = "ru-RU",
    user: dict = Depends(get_current_user)
):
    """Get Google Cloud TTS voices (cached)."""
    gcloud = get_google_cloud_tts()
    result = await gcloud.list_voices(language_code=language)
    if not result.get("success"):
        logger.warning("Google Cloud voices unavailable: %s", result.get("error", "unknown error"))
        return {
            "voices": [],
            "cached": False,
            "available": False,
            "error": result.get("error"),
            "hint": result.get("hint"),
            "status_code": result.get("status_code"),
        }
    return {
        "voices": result.get("voices", []),
        "cached": result.get("cached", False),
        "available": True,
        "auth_mode": result.get("auth_mode"),
    }


@router.post("/gcloud/voices")
async def set_gcloud_voices(
    request: GcloudVoiceSelectionRequest,
    user: dict = Depends(get_current_user),
    service: TTSService = Depends(get_tts_service)
):
    """Persist selected Google Cloud TTS voices for user."""
    voices = [
        v.strip()
        for v in request.voices
        if isinstance(v, str) and v.strip() and is_gemini_or_chirp_voice(v.strip())
    ]
    if not voices:
        raise HTTPException(status_code=400, detail="Select at least one Gemini or Chirp3-HD voice")
    result = await service.save_tts_settings(user_id=user['id'], gcloud_voices=voices)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail="Failed to save voices")
    return {"success": True, "voices": voices}


@router.post("/gcloud/preview")
async def preview_gcloud_voice(
    request: GcloudVoicePreviewRequest,
    user: dict = Depends(get_current_user),
    service: TTSService = Depends(get_tts_service),
):
    """Preview Google Cloud TTS voice with sample phrase."""
    requested_mood = request.mood
    if requested_mood is None:
        saved_settings = await service.get_tts_settings(user_id=user["id"])
        requested_mood = (
            saved_settings.get("gcloud_mood")
            or saved_settings.get("gcloudMood")
        )
    resolved_mood = normalize_gcloud_mood(requested_mood)

    gcloud = get_google_cloud_tts()
    result = await gcloud.synthesize_speech(
        text=request.text or "Hello! This is a Google Cloud voice preview.",
        voice_name=request.voice_name,
        volume_level=50.0,
        speed=1.0,
        mood=resolved_mood,
        model_name=request.model_name,
    )
    if not result.get("success"):
        status_code = result.get("status_code")
        http_status = 502 if status_code in {400, 401, 403, 429, 500} else 400
        raise HTTPException(
            status_code=http_status,
            detail={
                "error": result.get("error") or "Failed to synthesize preview",
                "hint": result.get("hint"),
                "status_code": status_code,
            },
        )

    audio_path = result.get("audio_path")
    if not audio_path:
        raise HTTPException(status_code=500, detail="No audio_path returned")

    filename = Path(audio_path).name
    audio_url = f"{settings.backend_url}/api/tts/audio/{filename}"
    return {
        "success": True,
        "audio_url": audio_url,
        "voice": result.get("voice"),
        "auth_mode": result.get("auth_mode"),
        "requested_model": result.get("requested_model"),
        "fallback_used": bool(result.get("fallback_used")),
        "mood": resolved_mood,
    }

# ============================================================================
# ADDITIONAL SETTINGS (Platform / Listening Mode)
# ============================================================================

@router.get("/platform-settings")
async def get_platform_settings(
    user: dict = Depends(get_current_user),
    service: TTSService = Depends(get_tts_service)
):
    """Get enabled platforms for TTS."""
    return await service.get_platform_settings(user_id=user['id'])

@router.post("/platform-settings")
async def set_platform_settings(
    settings_req: PlatformSettingsRequest,
    user: dict = Depends(get_current_user),
    service: TTSService = Depends(get_tts_service)
):
    """Set enabled platforms for TTS."""
    success = await service.set_platform_settings(
        user_id=user['id'],
        enabled_platforms=settings_req.enabled_platforms
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update platform settings")
    return {"success": True, **await service.get_platform_settings(user_id=user['id'])}


@router.get("/obs-status")
async def get_obs_status(
    user: dict = Depends(get_current_user),
    service: TTSService = Depends(get_tts_service)
):
    """Return OBS source and dock connection state."""
    from core.connection_manager import get_connection_manager
    from services.memory_websocket_manager import get_memory_websocket_manager

    user_row = service.user_repo.get_by_id(user["id"])
    source_token = getattr(user_row, "tts_source_token", None) if user_row else None
    legacy_token = getattr(user_row, "obs_token", None) if user_row else None
    source_connected = bool(
        (source_token and source_token in get_connection_manager().obs_connections)
        or (legacy_token and legacy_token in get_connection_manager().obs_connections)
    )
    dock_connected = get_memory_websocket_manager().has_user_connection_for_role(user["id"], "tts_player")
    return {
        "has_token": bool(source_token or legacy_token),
        "source_connected": source_connected,
        "dock_connected": dock_connected,
    }

@router.post("/listening-mode")
async def set_listening_mode(
    request: Request,
    user: dict = Depends(get_current_user),
    service: TTSService = Depends(get_tts_service)
):
    """Set listening mode."""
    data = await request.json()
    mode = data.get("listening_mode") or data.get("listeningMode")
    if mode not in {"website", "obs"}:
        raise HTTPException(status_code=400, detail="Mode must be 'website' or 'obs'")

    result = await service.save_tts_settings(user_id=user['id'], listening_mode=mode)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail="Failed to save listening mode")

    return {"success": True, "listening_mode": mode, "listeningMode": mode}




