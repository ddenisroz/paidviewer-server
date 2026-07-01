from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import urlparse

def resolve_provider_audio_fetch_headers(
    *,
    provider: str,
    endpoint: str,
    resolved_audio_url: str,
    headers: dict[str, str],
    gateway_url: str,
    get_provider_service_url_fn: Callable[[str], str],
    build_tts_auth_headers_fn: Callable[..., dict[str, str]],
) -> dict[str, str]:
    resolved_netloc = urlparse(resolved_audio_url).netloc.strip().lower()
    endpoint_netloc = urlparse(endpoint).netloc.strip().lower()
    if not resolved_netloc or resolved_netloc == endpoint_netloc:
        return headers

    provider_service_url = get_provider_service_url_fn(provider).rstrip("/")
    provider_service_netloc = urlparse(provider_service_url).netloc.strip().lower()
    if resolved_netloc == provider_service_netloc:
        provider_headers = build_tts_auth_headers_fn(
            provider=provider,
            upstream="voice",
            strict=False,
        )
        if provider_headers:
            return provider_headers

    gateway_netloc = urlparse(gateway_url).netloc.strip().lower()
    if resolved_netloc == gateway_netloc:
        gateway_headers = build_tts_auth_headers_fn(
            provider=provider,
            upstream="synthesis",
            use_gateway=True,
            strict=False,
        )
        if gateway_headers:
            return gateway_headers

    return headers


async def persist_audio_bytes(
    *,
    audio_bytes: bytes,
    provider: str,
    source_url: Optional[str],
    content_type: Optional[str],
    backend_url: str,
    temp_dir: Path,
) -> dict[str, str]:
    suffix = Path(urlparse(str(source_url or "")).path).suffix.lower()
    if suffix not in {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac", ".aiff", ".au", ".wma"}:
        normalized_content_type = str(content_type or "").lower()
        if "mpeg" in normalized_content_type or "mp3" in normalized_content_type:
            suffix = ".mp3"
        elif "ogg" in normalized_content_type:
            suffix = ".ogg"
        else:
            suffix = ".wav"

    output_dir = temp_dir / "tts_audio"
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{provider}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}{suffix}"
    output_path = output_dir / filename
    await asyncio.to_thread(output_path.write_bytes, audio_bytes)
    return {
        "audio_url": f"{backend_url}/api/tts/audio/{filename}",
        "audio_path": str(output_path.resolve()),
    }


async def materialize_provider_audio(
    *,
    session: Any,
    provider: str,
    audio_url: Optional[str],
    endpoint: str,
    headers: dict[str, str],
    backend_url: str,
    resolve_provider_audio_fetch_headers_fn: Callable[..., dict[str, str]],
    persist_audio_bytes_fn: Callable[..., Awaitable[dict[str, str]]],
) -> dict[str, Optional[str]]:
    raw_audio_url = str(audio_url or "").strip()
    if not raw_audio_url:
        return {"audio_url": None, "audio_path": None}

    if raw_audio_url.startswith(backend_url):
        return {"audio_url": raw_audio_url, "audio_path": None}

    if raw_audio_url.startswith(("http://", "https://")):
        resolved_audio_url = raw_audio_url
    elif raw_audio_url.startswith("/"):
        resolved_audio_url = f"{endpoint}{raw_audio_url}"
    else:
        resolved_audio_url = f"{endpoint}/api/tts/audio/{raw_audio_url}"

    if resolved_audio_url.startswith(backend_url):
        return {"audio_url": resolved_audio_url, "audio_path": None}

    fetch_headers = resolve_provider_audio_fetch_headers_fn(
        provider=provider,
        endpoint=endpoint,
        resolved_audio_url=resolved_audio_url,
        headers=headers,
    )

    async with session.get(resolved_audio_url, headers=fetch_headers) as audio_response:
        if audio_response.status != 200:
            body = await audio_response.text()
            raise RuntimeError(
                f"Provider audio fetch failed provider={provider} status={audio_response.status} body={body[:200]}"
            )
        audio_bytes = await audio_response.read()
        if not audio_bytes:
            raise RuntimeError(f"Provider audio fetch returned empty payload provider={provider}")
        return await persist_audio_bytes_fn(
            audio_bytes=audio_bytes,
            provider=provider,
            source_url=resolved_audio_url,
            content_type=audio_response.headers.get("content-type"),
        )


async def build_provider_success_result(
    *,
    session: Any,
    provider: str,
    endpoint: str,
    headers: dict[str, str],
    tts_type: str,
    result_payload: dict[str, Any],
    volume_level: float,
    materialize_provider_audio_fn: Callable[..., Awaitable[dict[str, Optional[str]]]],
) -> dict[str, Any]:
    if result_payload.get("success") is False:
        upstream_error = str(
            result_payload.get("error")
            or result_payload.get("detail")
            or "Provider returned unsuccessful payload"
        ).strip()
        raise RuntimeError(
            f"Provider returned unsuccessful payload provider={provider} error={upstream_error}"
        )

    raw_audio_url = str(result_payload.get("audio_url") or "").strip()
    if not raw_audio_url:
        upstream_error = str(result_payload.get("error") or result_payload.get("detail") or "").strip()
        raise RuntimeError(
            "Provider success payload missing audio_url "
            f"provider={provider} error={upstream_error or '-'} keys={sorted(result_payload.keys())}"
        )

    selected_voice = result_payload.get("selected_voice") or result_payload.get("voice")
    localized_audio = await materialize_provider_audio_fn(
        session=session,
        provider=provider,
        audio_url=raw_audio_url,
        endpoint=endpoint,
        headers=headers,
    )
    return {
        "success": True,
        "voice": selected_voice,
        "volume": volume_level,
        "tts_type": tts_type,
        "audio_url": localized_audio.get("audio_url"),
        "audio_path": localized_audio.get("audio_path"),
        "duration": result_payload.get("duration"),
        "spoken_text": result_payload.get("spoken_text"),
        "meta": result_payload.get("meta") if isinstance(result_payload.get("meta"), dict) else {},
        "speed_preset": result_payload.get("speed_preset")
        or (
            result_payload.get("meta", {}).get("speed_preset")
            if isinstance(result_payload.get("meta"), dict)
            else None
        ),
        "speed_factor": result_payload.get("speed_factor")
        or (
            result_payload.get("meta", {}).get("speed_factor")
            if isinstance(result_payload.get("meta"), dict)
            else None
        ),
    }
