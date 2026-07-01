from __future__ import annotations

from typing import Any

from services.tts.provider_utils import infer_provider_from_engine, normalize_provider_mode


def resolve_requested_provider(
    *,
    resolved_engine: str,
    settings_dict: dict[str, Any],
) -> str:
    if resolved_engine == "f5tts":
        return infer_provider_from_engine(
            resolved_engine,
            advanced_provider=settings_dict.get("advanced_provider"),
        )
    if resolved_engine == "gcloud":
        return "gcloud"
    return "gtts"


def resolve_advanced_provider_mode(
    *,
    provider: str,
    settings_dict: dict[str, Any],
) -> tuple[str, bool]:
    _ = provider
    provider_mode_key = "f5_mode"
    preferred_mode = normalize_provider_mode(settings_dict.get(provider_mode_key))
    has_explicit_provider_mode = (
        provider_mode_key in settings_dict and settings_dict.get(provider_mode_key) is not None
    )
    if has_explicit_provider_mode:
        return preferred_mode, True
    if bool(settings_dict.get("use_local_tts", False)):
        return "local", False
    return preferred_mode, False
