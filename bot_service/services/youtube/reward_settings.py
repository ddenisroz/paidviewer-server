"""Utilities for canonical YouTube reward settings handling."""

from __future__ import annotations

from typing import Any, Literal, Mapping, Optional

RewardPlatform = Literal["twitch", "vk"]
ObsOverlayMode = Literal["video", "track"]

LEGACY_REWARD_KEYS = (
    "requests_reward_enabled",
    "requests_reward_id",
    "requests_reward_platform",
)

CANONICAL_REWARD_KEYS = (
    "requests_reward_twitch_enabled",
    "requests_reward_twitch_id",
    "requests_reward_vk_enabled",
    "requests_reward_vk_id",
)

DONATIONALERTS_VIDEO_KEYS = (
    "donationalerts_video_enabled",
    "donationalerts_video_min_amount",
    "donationalerts_video_priority_next",
)

PAID_ORDER_MODES = {"rub_per_minute", "full_video"}


def normalize_paid_order_mode(value: object) -> str:
    return str(value) if value in PAID_ORDER_MODES else "rub_per_minute"


def clean_optional_reward_value(value: object) -> Optional[str]:
    """Normalize reward identifiers/titles coming from API payloads or DB JSON."""

    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return None


def normalize_obs_overlay_mode(value: object) -> ObsOverlayMode:
    """Normalize YouTube OBS overlay mode."""

    return "video" if value == "video" else "track"


def normalize_reward_settings(youtube_settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a normalized reward view that keeps legacy response compatibility."""

    raw_settings = dict(youtube_settings or {})

    legacy_enabled = bool(raw_settings.get("requests_reward_enabled", False))
    legacy_platform: RewardPlatform = (
        "vk" if raw_settings.get("requests_reward_platform") == "vk" else "twitch"
    )
    legacy_reward_id = clean_optional_reward_value(raw_settings.get("requests_reward_id"))

    twitch_enabled_raw = raw_settings.get("requests_reward_twitch_enabled")
    vk_enabled_raw = raw_settings.get("requests_reward_vk_enabled")
    twitch_id_raw = raw_settings.get("requests_reward_twitch_id")
    vk_id_raw = raw_settings.get("requests_reward_vk_id")

    has_new_enabled = twitch_enabled_raw is not None or vk_enabled_raw is not None
    has_new_ids = twitch_id_raw is not None or vk_id_raw is not None

    if has_new_enabled:
        twitch_enabled = bool(twitch_enabled_raw)
        vk_enabled = bool(vk_enabled_raw)
    else:
        twitch_enabled = legacy_enabled and legacy_platform == "twitch"
        vk_enabled = legacy_enabled and legacy_platform == "vk"

    twitch_id = clean_optional_reward_value(twitch_id_raw)
    vk_id = clean_optional_reward_value(vk_id_raw)

    if not has_new_ids and legacy_reward_id:
        if legacy_platform == "twitch":
            twitch_id = legacy_reward_id
        else:
            vk_id = legacy_reward_id

    legacy_enabled_out = twitch_enabled or vk_enabled
    if twitch_enabled and vk_enabled:
        legacy_platform_out: RewardPlatform = "twitch" if twitch_id else ("vk" if vk_id else "twitch")
    elif vk_enabled:
        legacy_platform_out = "vk"
    else:
        legacy_platform_out = "twitch"

    legacy_reward_id_out = vk_id if legacy_platform_out == "vk" else twitch_id

    return {
        "requests_reward_enabled": legacy_enabled_out,
        "requests_reward_id": legacy_reward_id_out,
        "requests_reward_platform": legacy_platform_out,
        "requests_reward_twitch_enabled": twitch_enabled,
        "requests_reward_twitch_id": twitch_id,
        "requests_reward_vk_enabled": vk_enabled,
        "requests_reward_vk_id": vk_id,
    }


def canonicalize_youtube_settings(youtube_settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return canonical settings storage without legacy reward keys."""

    raw_settings = dict(youtube_settings or {})
    reward_settings = normalize_reward_settings(raw_settings)

    canonical = dict(raw_settings)
    for key in LEGACY_REWARD_KEYS:
        canonical.pop(key, None)

    canonical.update(
        {
            "requests_reward_twitch_enabled": reward_settings["requests_reward_twitch_enabled"],
            "requests_reward_twitch_id": reward_settings["requests_reward_twitch_id"],
            "requests_reward_vk_enabled": reward_settings["requests_reward_vk_enabled"],
            "requests_reward_vk_id": reward_settings["requests_reward_vk_id"],
        }
    )
    return canonical


def build_youtube_settings_response(youtube_settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """Build API response payload with canonical + legacy-compatible reward fields."""

    canonical = canonicalize_youtube_settings(youtube_settings)
    reward_settings = normalize_reward_settings(canonical)
    return {
        "playback_mode": canonical.get("playback_mode", "browser"),
        "obs_overlay_mode": normalize_obs_overlay_mode(canonical.get("obs_overlay_mode", "track")),
        "volume_level": canonical.get("volume_level", 100),
        "requests_command_enabled": canonical.get("requests_command_enabled", True),
        "request_command_name": str(canonical.get("request_command_name") or "!sr"),
        "paid_orders_enabled": bool(
            canonical.get("paid_orders_enabled", canonical.get("donationalerts_video_enabled", False))
        ),
        "paid_order_mode": normalize_paid_order_mode(canonical.get("paid_order_mode", "rub_per_minute")),
        "paid_order_rate_rub_per_minute": float(
            canonical.get(
                "paid_order_rate_rub_per_minute",
                canonical.get("donationalerts_video_min_amount", 0),
            )
            or 0
        ),
        "paid_order_min_amount_rub": float(
            canonical.get(
                "paid_order_min_amount_rub",
                canonical.get("donationalerts_video_min_amount", 0),
            )
            or 0
        ),
        "paid_order_priority_by_amount": bool(
            canonical.get(
                "paid_order_priority_by_amount",
                canonical.get("donationalerts_video_priority_next", True),
            )
        ),
        "donationalerts_video_enabled": bool(canonical.get("donationalerts_video_enabled", False)),
        "donationalerts_video_min_amount": float(canonical.get("donationalerts_video_min_amount", 0) or 0),
        "donationalerts_video_priority_next": bool(canonical.get("donationalerts_video_priority_next", True)),
        **reward_settings,
    }


def apply_youtube_settings_update(
    current_settings: Mapping[str, Any] | None,
    updates: Mapping[str, Any],
) -> dict[str, Any]:
    """Merge an update payload into the current settings and return canonical storage."""

    current_canonical = canonicalize_youtube_settings(current_settings)
    merged = dict(current_canonical)

    for key, value in dict(updates).items():
        if key not in LEGACY_REWARD_KEYS and key not in CANONICAL_REWARD_KEYS:
            merged[key] = value

    reward_view = normalize_reward_settings(current_canonical)
    update_map = dict(updates)
    has_new_enabled_updates = any(
        key in update_map for key in ("requests_reward_twitch_enabled", "requests_reward_vk_enabled")
    )
    has_new_id_updates = any(
        key in update_map for key in ("requests_reward_twitch_id", "requests_reward_vk_id")
    )

    if "requests_reward_twitch_enabled" in update_map:
        reward_view["requests_reward_twitch_enabled"] = bool(update_map["requests_reward_twitch_enabled"])
    if "requests_reward_vk_enabled" in update_map:
        reward_view["requests_reward_vk_enabled"] = bool(update_map["requests_reward_vk_enabled"])
    if "requests_reward_twitch_id" in update_map:
        reward_view["requests_reward_twitch_id"] = clean_optional_reward_value(update_map["requests_reward_twitch_id"])
    if "requests_reward_vk_id" in update_map:
        reward_view["requests_reward_vk_id"] = clean_optional_reward_value(update_map["requests_reward_vk_id"])

    legacy_platform: RewardPlatform = (
        "vk"
        if update_map.get("requests_reward_platform", reward_view["requests_reward_platform"]) == "vk"
        else "twitch"
    )

    if not has_new_enabled_updates and (
        "requests_reward_enabled" in update_map or "requests_reward_platform" in update_map
    ):
        if "requests_reward_enabled" in update_map:
            legacy_enabled = bool(update_map["requests_reward_enabled"])
        else:
            legacy_enabled = bool(
                reward_view["requests_reward_twitch_enabled"] or reward_view["requests_reward_vk_enabled"]
            )

        reward_view["requests_reward_twitch_enabled"] = legacy_enabled and legacy_platform == "twitch"
        reward_view["requests_reward_vk_enabled"] = legacy_enabled and legacy_platform == "vk"

    if "requests_reward_id" in update_map and not has_new_id_updates:
        legacy_reward_id = clean_optional_reward_value(update_map["requests_reward_id"])
        if legacy_platform == "vk":
            reward_view["requests_reward_vk_id"] = legacy_reward_id
        else:
            reward_view["requests_reward_twitch_id"] = legacy_reward_id

    merged.update(
        {
            "requests_reward_twitch_enabled": reward_view["requests_reward_twitch_enabled"],
            "requests_reward_twitch_id": reward_view["requests_reward_twitch_id"],
            "requests_reward_vk_enabled": reward_view["requests_reward_vk_enabled"],
            "requests_reward_vk_id": reward_view["requests_reward_vk_id"],
            "request_command_name": str(merged.get("request_command_name") or "!sr").strip() or "!sr",
            "paid_orders_enabled": bool(merged.get("paid_orders_enabled", merged.get("donationalerts_video_enabled", False))),
            "paid_order_mode": normalize_paid_order_mode(merged.get("paid_order_mode", "rub_per_minute")),
            "paid_order_rate_rub_per_minute": max(
                0.0,
                float(
                    merged.get(
                        "paid_order_rate_rub_per_minute",
                        merged.get("donationalerts_video_min_amount", 0),
                    )
                    or 0
                ),
            ),
            "paid_order_min_amount_rub": max(
                0.0,
                float(
                    merged.get(
                        "paid_order_min_amount_rub",
                        merged.get("donationalerts_video_min_amount", 0),
                    )
                    or 0
                ),
            ),
            "paid_order_priority_by_amount": bool(
                merged.get("paid_order_priority_by_amount", merged.get("donationalerts_video_priority_next", True))
            ),
            "donationalerts_video_enabled": bool(merged.get("donationalerts_video_enabled", merged.get("paid_orders_enabled", False))),
            "donationalerts_video_min_amount": max(
                0.0,
                float(
                    merged.get(
                        "donationalerts_video_min_amount",
                        merged.get("paid_order_rate_rub_per_minute", merged.get("paid_order_min_amount_rub", 0)),
                    )
                    or 0
                ),
            ),
            "donationalerts_video_priority_next": bool(
                merged.get("donationalerts_video_priority_next", merged.get("paid_order_priority_by_amount", True))
            ),
        }
    )
    return canonicalize_youtube_settings(merged)


def get_platform_reward_configuration(
    youtube_settings: Mapping[str, Any] | None,
    *,
    platform: RewardPlatform,
) -> dict[str, Any]:
    """Return reward enablement and value for a specific platform."""

    normalized = normalize_reward_settings(youtube_settings)
    if platform == "vk":
        return {
            "enabled": normalized["requests_reward_vk_enabled"],
            "reward_value": normalized["requests_reward_vk_id"],
        }
    return {
        "enabled": normalized["requests_reward_twitch_enabled"],
        "reward_value": normalized["requests_reward_twitch_id"],
    }
