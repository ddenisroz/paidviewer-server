"""
Lightweight error reporting endpoint for frontend error boundaries.
"""
import logging
import json
from typing import Any, Dict

from fastapi import APIRouter, Request, HTTPException
from core.security_modern import limiter

logger = logging.getLogger(__name__)

router = APIRouter()

SENSITIVE_KEYS = {"authorization", "token", "access_token", "refresh_token", "password", "secret", "api_key"}
MAX_LOG_PAYLOAD_CHARS = 4000
MAX_REQUEST_BODY_BYTES = 16 * 1024


async def _read_body_limited(request: Request, max_bytes: int) -> bytes:
    data = bytearray()
    async for chunk in request.stream():
        if not chunk:
            continue
        data.extend(chunk)
        if len(data) > max_bytes:
            raise HTTPException(status_code=413, detail="Payload too large")
    return bytes(data)


def _redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: Dict[str, Any] = {}
        for key, item in value.items():
            key_lower = str(key).lower()
            if key_lower in SENSITIVE_KEYS:
                redacted[key] = "***redacted***"
            else:
                redacted[key] = _redact_sensitive(item)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_sensitive(item) for item in value)
    return value


def _serialize_safe_payload(payload: Any) -> str:
    safe_payload = _redact_sensitive(payload)
    safe_payload_text = str(safe_payload)
    if len(safe_payload_text) > MAX_LOG_PAYLOAD_CHARS:
        return f"{safe_payload_text[:MAX_LOG_PAYLOAD_CHARS]}...<truncated>"
    return safe_payload_text


@router.post("/api/errors/report")
@limiter.limit("60/minute")
async def report_frontend_error(request: Request) -> Dict[str, Any]:
    content_length_raw = request.headers.get("content-length")
    if content_length_raw:
        try:
            if int(content_length_raw) > MAX_REQUEST_BODY_BYTES:
                raise HTTPException(status_code=413, detail="Payload too large")
        except ValueError:
            pass

    max_body_bytes = 8192
    raw_body = await _read_body_limited(request, MAX_REQUEST_BODY_BYTES)

    try:
        payload = json.loads(raw_body.decode("utf-8", errors="replace")) if raw_body else {}
    except Exception:
        payload = {"raw": raw_body[:max_body_bytes].decode("utf-8", errors="replace")}

    logger.error("[FRONTEND ERROR] %s", _serialize_safe_payload(payload))
    return {"success": True}
