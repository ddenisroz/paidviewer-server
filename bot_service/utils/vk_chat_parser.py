"""
Helpers to parse VK Live chat payloads into text, emotes, and badge URLs.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)
_MENTION_RE = re.compile(r"@([A-Za-z0-9_\.]+)")


def _normalize_vk_asset_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return url
    normalized = str(url).strip()
    if not normalized:
        return None
    if normalized.startswith("//"):
        return f"https:{normalized}"
    if normalized.startswith("/"):
        return f"https://images.live.vkvideo.ru{normalized}"
    return normalized


def _build_vk_asset_url(kind: str, asset_id: Optional[Any], size: str = "small", change_time: Optional[Any] = None) -> Optional[str]:
    if not asset_id:
        return None
    url = f"https://images.live.vkvideo.ru/{kind}/{asset_id}/icon/size/{size}"
    if change_time:
        return f"{url}?change_time={change_time}"
    return url


def normalize_parts(parts: Optional[List[Dict[str, Any]]], data_blocks: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """
    Normalize VK message payloads into `parts` shape.

    VK Live may send either `parts` (objects with text/smile/mention/link)
    or `data` blocks (editor-like payload). We convert data blocks to text parts
    so downstream parsing stays consistent.
    """
    if parts:
        return parts

    normalized: List[Dict[str, Any]] = []
    if not data_blocks:
        return normalized

    for block in data_blocks:
        if not isinstance(block, dict):
            continue

        block_type = str(block.get("type") or "").lower()
        content = block.get("content")

        if block_type in {"text", "plain_text"}:
            if isinstance(content, str) and content.startswith("["):
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, list) and parsed:
                        content = parsed[0]
                except Exception:
                    pass
            normalized.append({"text": {"content": str(content or "")}})
            continue

        if block_type in {"smile", "emote", "emoji"}:
            smile_payload = block.get("smile")
            if not isinstance(smile_payload, dict):
                smile_payload = content if isinstance(content, dict) else block
            if isinstance(smile_payload, dict):
                normalized.append({"smile": smile_payload})
            continue

        if block_type == "mention":
            mention_payload = block.get("mention")
            if not isinstance(mention_payload, dict):
                mention_payload = content if isinstance(content, dict) else block
            if isinstance(mention_payload, dict):
                normalized.append({"mention": mention_payload})
            continue

        if block_type == "link":
            link_payload = block.get("link")
            if not isinstance(link_payload, dict):
                link_payload = content if isinstance(content, dict) else block
            if isinstance(link_payload, dict):
                normalized.append({"link": link_payload})
            continue

    return normalized


def extract_vk_badge_urls(author: Dict[str, Any]) -> Optional[List[str]]:
    badge_sources: List[Any] = []
    for source_key in ("badges", "roles", "channel_points", "channelPoints", "awards"):
        source = author.get(source_key)
        if isinstance(source, list):
            badge_sources.extend(source)
        elif source:
            badge_sources.append(source)

    if not badge_sources:
        return None

    urls: List[str] = []
    for badge in badge_sources:
        if isinstance(badge, str):
            normalized = _normalize_vk_asset_url(badge)
            if normalized:
                urls.append(normalized)
            continue
        if not isinstance(badge, dict):
            continue
        url = (
            badge.get("largeUrl")
            or badge.get("large_url")
            or badge.get("mediumUrl")
            or badge.get("medium_url")
            or badge.get("smallUrl")
            or badge.get("small_url")
            or badge.get("url")
            or badge.get("icon")
            or badge.get("small")
            or badge.get("image")
        )
        if not url:
            badge_kind = (
                badge.get("type")
                or badge.get("kind")
                or badge.get("category")
                or badge.get("entity")
            )
            badge_id = badge.get("id") or badge.get("uuid") or badge.get("badge_id")
            change_time = badge.get("change_time") or badge.get("changeTime")

            kind_map = {
                "role": "role",
                "badge": "badge",
                "channel_point": "channel_point",
                "channelpoint": "channel_point",
            }
            mapped_kind = kind_map.get(str(badge_kind).lower()) if badge_kind else None
            if mapped_kind:
                url = _build_vk_asset_url(mapped_kind, badge_id, size="small", change_time=change_time)

        normalized = _normalize_vk_asset_url(url)
        if normalized:
            urls.append(normalized)

    return urls or None


def extract_smile_url(smile: Dict[str, Any]) -> Optional[str]:
    url = (
        smile.get("largeUrl")
        or smile.get("large_url")
        or smile.get("mediumUrl")
        or smile.get("medium_url")
        or smile.get("smallUrl")
        or smile.get("small_url")
        or smile.get("url")
        or smile.get("icon")
        or smile.get("small")
        or smile.get("src")
    )
    if url:
        return _normalize_vk_asset_url(url)

    smile_id = smile.get("id") or smile.get("smile_id") or smile.get("uuid")
    if smile_id:
        change_time = smile.get("change_time") or smile.get("changeTime")
        return _build_vk_asset_url("smile", smile_id, size="large", change_time=change_time)
    return None


def build_message_text_and_emotes(parts: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    message_text = ""
    emotes: List[Dict[str, Any]] = []
    cursor = 0

    for part in parts:
        if "text" in part:
            content = part["text"].get("content", "")
            content = str(content)
            message_text += content
            cursor += len(content)
            continue

        if "mention" in part:
            mention = f"@{part['mention'].get('nick', '')}"
            message_text += mention
            cursor += len(mention)
            continue

        if "smile" in part:
            smile = part.get("smile") or {}
            if not isinstance(smile, dict):
                continue
            smile_id = smile.get("id") or smile.get("smile_id") or smile.get("uuid")
            name = smile.get("name") or smile.get("baseName") or (f"smile_{smile_id}" if smile_id else "smile")
            placeholder = f":{name}:"
            start = cursor
            end = start + len(placeholder) - 1
            message_text += placeholder
            cursor += len(placeholder)

            url = extract_smile_url(smile)
            if url:
                emotes.append({
                    "id": smile_id or name,
                    "name": name,
                    "url": url,
                    "start": start,
                    "end": end
                })
            continue

        if "link" in part:
            link_url = part["link"].get("url", "")
            if link_url:
                message_text += link_url
                cursor += len(link_url)

    return message_text, emotes


def extract_vk_mentioned_users(
    parts: Optional[List[Dict[str, Any]]],
    data_blocks: Optional[List[Dict[str, Any]]] = None,
    fallback_text: Optional[str] = None,
) -> List[str]:
    normalized_parts = normalize_parts(parts, data_blocks)
    mentioned_users: List[str] = []

    for part in normalized_parts:
        mention = part.get("mention")
        if not isinstance(mention, dict):
            continue
        candidate = (
            mention.get("nick")
            or mention.get("name")
            or mention.get("username")
            or mention.get("login")
        )
        if not candidate:
            continue
        normalized = str(candidate).strip().lstrip("@").lower()
        if normalized and normalized not in mentioned_users:
            mentioned_users.append(normalized)

    if fallback_text:
        for match in _MENTION_RE.findall(fallback_text):
            normalized = str(match).strip().lstrip("@").lower()
            if normalized and normalized not in mentioned_users:
                mentioned_users.append(normalized)

    return mentioned_users


def extract_vk_reply_metadata(message: Optional[Dict[str, Any]]) -> Dict[str, Optional[str] | bool]:
    if not isinstance(message, dict):
        return {
            "is_reply": False,
            "reply_to_author": None,
            "reply_to_text": None,
        }

    reply_candidate = None
    for key in ("reply", "reply_message", "replyMessage", "reply_to", "reply_to_message"):
        candidate = message.get(key)
        if isinstance(candidate, dict):
            reply_candidate = candidate
            break

    if not isinstance(reply_candidate, dict):
        return {
            "is_reply": False,
            "reply_to_author": None,
            "reply_to_text": None,
        }

    author = reply_candidate.get("author")
    reply_to_author = None
    if isinstance(author, dict):
        reply_to_author = (
            author.get("nick")
            or author.get("name")
            or author.get("username")
            or author.get("login")
        )
    if not reply_to_author:
        reply_to_author = (
            reply_candidate.get("author_nick")
            or reply_candidate.get("author_name")
            or reply_candidate.get("username")
            or reply_candidate.get("nick")
            or reply_candidate.get("name")
        )

    reply_to_text = (
        reply_candidate.get("text")
        or reply_candidate.get("message")
        or reply_candidate.get("content")
    )
    if not reply_to_text:
        reply_parts = normalize_parts(reply_candidate.get("parts"), reply_candidate.get("data"))
        reply_to_text, _ = build_message_text_and_emotes(reply_parts)

    normalized_text = str(reply_to_text).strip() if reply_to_text else None
    if normalized_text:
        normalized_text = normalized_text[:120]

    return {
        "is_reply": True,
        "reply_to_author": str(reply_to_author).strip() if reply_to_author else None,
        "reply_to_text": normalized_text,
    }
