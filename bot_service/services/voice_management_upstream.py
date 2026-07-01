from __future__ import annotations

import logging
from typing import Any, Optional

import httpx
from fastapi import HTTPException

from core.internal_service_auth import (
    TTSAuthConfigError,
    build_tts_auth_headers,
    build_tts_httpx_client_kwargs,
)
from services.tts.provider_utils import (
    ProviderRoutingError,
    get_voice_management_upstream_params,
    get_voice_management_upstream_url,
    normalize_provider,
)

logger = logging.getLogger(__name__)


def resolve_provider(provider: str = "f5") -> str:
    return normalize_provider(provider)


def ensure_voice_management_provider(provider: str = "f5") -> str:
    normalized = resolve_provider(provider)
    if normalized == "gcloud":
        raise HTTPException(
            status_code=400,
            detail={
                "code": "gcloud_voice_management_not_supported",
                "message": "Google Cloud provider does not support voice CRUD in bot_service.",
            },
        )
    return normalized


def provider_tts_api_base(provider: str = "f5") -> str:
    resolved_provider = ensure_voice_management_provider(provider)
    try:
        provider_url = get_voice_management_upstream_url(resolved_provider)
    except ProviderRoutingError as error:
        raise HTTPException(status_code=400, detail={"code": str(error), "message": str(error)}) from error
    return f"{provider_url.rstrip('/')}/api/tts"


def provider_admin_api_base(provider: str = "f5") -> str:
    resolved_provider = ensure_voice_management_provider(provider)
    try:
        provider_url = get_voice_management_upstream_url(resolved_provider)
    except ProviderRoutingError as error:
        raise HTTPException(status_code=400, detail={"code": str(error), "message": str(error)}) from error
    return f"{provider_url.rstrip('/')}/api/admin"


def tts_auth_headers(provider: str) -> dict[str, str]:
    try:
        return build_tts_auth_headers(
            provider=ensure_voice_management_provider(provider),
            upstream="voice",
            strict=True,
        )
    except TTSAuthConfigError as error:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "tts_upstream_auth_not_configured",
                "message": str(error),
            },
        ) from error


def provider_request_params(
    provider: str = "f5",
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    return get_voice_management_upstream_params(
        ensure_voice_management_provider(provider),
        extra_params=extra,
    )


def raise_upstream_http_error(
    *,
    response: httpx.Response,
    operation: str,
    default_detail: str,
) -> None:
    status_code = response.status_code
    raw_body = (response.text or "").strip()
    if raw_body:
        logger.warning(
            "Voice upstream error during %s: status=%s body=%s",
            operation,
            status_code,
            raw_body[:500],
        )
    else:
        logger.warning("Voice upstream error during %s: status=%s", operation, status_code)

    detail = default_detail
    try:
        payload = response.json()
        if isinstance(payload, dict):
            detail = (
                str(payload.get("detail") or payload.get("message") or payload.get("error") or "").strip()
                or default_detail
            )
    except Exception:
        pass

    if status_code in (401, 403):
        raise HTTPException(status_code=503, detail="TTS service authorization failed")

    raise HTTPException(status_code=status_code, detail=detail)


def raise_upstream_transport_error(
    *,
    error: Exception,
    operation: str,
    timeout_detail: str,
    connect_detail: str,
) -> None:
    if isinstance(error, httpx.TimeoutException):
        logger.warning("Voice upstream timeout during %s: %s", operation, error)
        raise HTTPException(
            status_code=504,
            detail={
                "code": "tts_voice_upstream_timeout",
                "message": timeout_detail,
                "operation": operation,
            },
        ) from error

    if isinstance(error, httpx.RequestError):
        logger.warning("Voice upstream connection error during %s: %s", operation, error)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "tts_voice_upstream_unreachable",
                "message": connect_detail,
                "operation": operation,
            },
        ) from error

    logger.exception("Voice upstream unexpected failure during %s", operation)
    raise HTTPException(status_code=500, detail="Internal server error") from error


class VoiceManagementUpstreamClient:
    """Shared httpx wrapper for voice CRUD requests."""

    async def request(
        self,
        method: str,
        *,
        url: str,
        timeout: float,
        operation: str,
        timeout_detail: str,
        connect_detail: str,
        **request_kwargs: Any,
    ) -> httpx.Response:
        try:
            async with httpx.AsyncClient(timeout=timeout, **build_tts_httpx_client_kwargs()) as client:
                request_method = getattr(client, method)
                return await request_method(url, **request_kwargs)
        except HTTPException:
            raise
        except Exception as error:
            raise_upstream_transport_error(
                error=error,
                operation=operation,
                timeout_detail=timeout_detail,
                connect_detail=connect_detail,
            )
