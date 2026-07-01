"""Helpers for extracting reply and mention context for TTS filtering."""

from __future__ import annotations

import re
from typing import Any

_MENTION_RE = re.compile(r"@([A-Za-z0-9_\.]+)")


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = str(item or "").strip().lstrip("@").lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def extract_twitch_tts_context(message: Any) -> dict[str, Any]:
    """Extract reply and mention context from a Twitch message object."""
    tags = getattr(message, "tags", None) or {}
    content = getattr(message, "content", "") or ""

    is_reply = bool(
        tags.get("reply-parent-msg-id")
        or tags.get("reply-parent-user-id")
        or tags.get("reply-parent-user-login")
        or tags.get("reply-parent-display-name")
    )
    mentioned_users = _dedupe_preserve_order(_MENTION_RE.findall(content))

    return {
        "is_reply": is_reply,
        "mentioned_users": mentioned_users,
    }
