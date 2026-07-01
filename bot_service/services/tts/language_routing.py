from __future__ import annotations

import re
from typing import Any

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
MENTION_RE = re.compile(r"(?<!\w)@[\w.-]+", re.IGNORECASE)
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.\w+\b", re.IGNORECASE)
EMOTE_RE = re.compile(r":[^:\s]{2,}:")
LATIN_WORD_RE = re.compile(r"\b[a-zA-Z][a-zA-Z'-]{1,}\b")
CYRILLIC_WORD_RE = re.compile(r"\b[а-яА-ЯёЁ][а-яА-ЯёЁ'-]{1,}\b")


def _sanitize_for_detection(text: str) -> str:
    sanitized = URL_RE.sub(" ", text)
    sanitized = EMAIL_RE.sub(" ", sanitized)
    sanitized = MENTION_RE.sub(" ", sanitized)
    sanitized = EMOTE_RE.sub(" ", sanitized)
    return sanitized


def detect_language_routing(text: str) -> dict[str, Any]:
    normalized_text = str(text or "")
    sanitized = _sanitize_for_detection(normalized_text)

    latin_words = LATIN_WORD_RE.findall(sanitized)
    cyrillic_words = CYRILLIC_WORD_RE.findall(sanitized)

    unique_latin_preview: list[str] = []
    seen: set[str] = set()
    for word in latin_words:
        normalized = word.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        unique_latin_preview.append(word)
        if len(unique_latin_preview) >= 5:
            break

    has_plain_latin_words = bool(latin_words)
    has_cyrillic_words = bool(cyrillic_words)

    if has_plain_latin_words and has_cyrillic_words:
        route_target = "mixed_en_bilingual"
        decision_reason = "mixed_cyrillic_and_plain_latin_words"
        detected_language = "mixed"
    elif has_plain_latin_words:
        route_target = "en_bilingual"
        decision_reason = "plain_latin_words_only"
        detected_language = "en"
    else:
        route_target = "ru_misha"
        decision_reason = "cyrillic_only_or_no_plain_latin_words"
        detected_language = "ru"

    return {
        "detected_language": detected_language,
        "route_target": route_target,
        "requires_bilingual_checkpoint": route_target != "ru_misha",
        "decision_reason": decision_reason,
        "plain_latin_words_preview": unique_latin_preview,
        "plain_latin_word_count": len(latin_words),
        "cyrillic_word_count": len(cyrillic_words),
    }


def enrich_tts_settings_with_language_routing(settings: dict[str, Any] | None, text: str) -> dict[str, Any]:
    next_settings = dict(settings or {})
    next_settings["language_routing"] = detect_language_routing(text)
    return next_settings
