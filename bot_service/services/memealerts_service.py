# bot_service/services/memealerts_service.py
"""
MemeAlerts service helpers for commands and API.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
import jwt
from sqlalchemy.orm import Session

from models.drops import MemeAlertsGrantHistory
from repositories.tts_settings_repository import TTSSettingsRepository
from repositories.user_token_repository import UserTokenRepository

logger = logging.getLogger(__name__)

MEMEALERTS_API_BASE = "https://memealerts.com/api"
MEMEALERTS_OBJECT_ID_RE = re.compile(r"^[a-fA-F0-9]{24}$")
MEMEALERTS_BROWSER_HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/144.0.0.0 Safari/537.36"
    ),
}

DEFAULT_MEMEALERTS_SETTINGS: Dict[str, Any] = {
    "points_reward": {
        "twitch": {
            "enabled": False,
            "reward_id": None,
            "reward_title": None,
            "coins_amount": 10,
            "reward_cost": 500,
        },
        "vk": {
            "enabled": False,
            "reward_id": None,
            "reward_title": None,
            "coins_amount": 10,
            "reward_cost": 500,
        },
    },
    "points_rewards": [],
    "donation_auto": {
        "enabled": False,
        "coins_per_currency": 1.0,
        "min_donation_amount": 1.0,
    },
}


class MemeAlertsService:
    def __init__(self, db: Session):
        self.db = db
        self.token_repo = UserTokenRepository(db)
        self.tts_repo = TTSSettingsRepository(db)

    @staticmethod
    def _clean_optional_str(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _safe_int(value: Any, default: int, *, minimum: int = 0, maximum: int = 1_000_000) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        if parsed < minimum:
            return minimum
        if parsed > maximum:
            return maximum
        return parsed

    @staticmethod
    def _safe_float(value: Any, default: float, *, minimum: float = 0.0, maximum: float = 1_000_000.0) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = default
        if parsed < minimum:
            return minimum
        if parsed > maximum:
            return maximum
        return parsed

    @staticmethod
    def _normalize_reward_item(raw: Dict[str, Any], fallback_platform: Optional[str] = None) -> Dict[str, Any]:
        platform = str(raw.get("platform") or fallback_platform or "").strip().lower()
        if platform not in ("twitch", "vk"):
            platform = "twitch"
        title_default = "MemeCoins" if platform == "twitch" else "Награда MemeCoins"
        return {
            "local_id": MemeAlertsService._clean_optional_str(raw.get("local_id")) or uuid.uuid4().hex,
            "platform": platform,
            "enabled": bool(raw.get("enabled", False)),
            "reward_id": MemeAlertsService._clean_optional_str(raw.get("reward_id")),
            "reward_title": MemeAlertsService._clean_optional_str(raw.get("reward_title")) or title_default,
            "coins_amount": MemeAlertsService._safe_int(raw.get("coins_amount"), 10, minimum=1),
            "reward_cost": MemeAlertsService._safe_int(raw.get("reward_cost"), 500, minimum=1),
            "cooldown_seconds": MemeAlertsService._safe_int(
                raw.get("cooldown_seconds"),
                0,
                minimum=0,
                maximum=86_400,
            ),
        }

    @staticmethod
    def _empty_platform_settings() -> Dict[str, Any]:
        return {
            "twitch": dict(DEFAULT_MEMEALERTS_SETTINGS["points_reward"]["twitch"]),
            "vk": dict(DEFAULT_MEMEALERTS_SETTINGS["points_reward"]["vk"]),
        }

    @staticmethod
    def _sync_legacy_points_reward(settings_payload: Dict[str, Any]) -> None:
        legacy = MemeAlertsService._empty_platform_settings()
        for item in settings_payload.get("points_rewards", []):
            if not isinstance(item, dict):
                continue
            platform = item.get("platform")
            if platform not in legacy:
                continue
            if legacy[platform].get("reward_id"):
                continue
            legacy[platform] = {
                "enabled": bool(item.get("enabled")),
                "reward_id": MemeAlertsService._clean_optional_str(item.get("reward_id")),
                "reward_title": MemeAlertsService._clean_optional_str(item.get("reward_title")),
                "coins_amount": MemeAlertsService._safe_int(item.get("coins_amount"), 10, minimum=1),
                "reward_cost": MemeAlertsService._safe_int(item.get("reward_cost"), 500, minimum=1),
            }
        settings_payload["points_reward"] = legacy

    @staticmethod
    def _normalize_settings(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        data = raw if isinstance(raw, dict) else {}
        points_raw = data.get("points_reward") if isinstance(data.get("points_reward"), dict) else {}
        points_rewards_raw = data.get("points_rewards") if isinstance(data.get("points_rewards"), list) else []
        donation_raw = data.get("donation_auto") if isinstance(data.get("donation_auto"), dict) else {}
        twitch_raw = points_raw.get("twitch") if isinstance(points_raw.get("twitch"), dict) else {}
        vk_raw = points_raw.get("vk") if isinstance(points_raw.get("vk"), dict) else {}

        normalized: Dict[str, Any] = {
            "points_reward": {
                "twitch": {
                    "enabled": bool(twitch_raw.get("enabled", False)),
                    "reward_id": MemeAlertsService._clean_optional_str(twitch_raw.get("reward_id")),
                    "reward_title": MemeAlertsService._clean_optional_str(twitch_raw.get("reward_title")),
                    "coins_amount": MemeAlertsService._safe_int(
                        twitch_raw.get("coins_amount"),
                        DEFAULT_MEMEALERTS_SETTINGS["points_reward"]["twitch"]["coins_amount"],
                        minimum=1,
                    ),
                    "reward_cost": MemeAlertsService._safe_int(
                        twitch_raw.get("reward_cost"),
                        DEFAULT_MEMEALERTS_SETTINGS["points_reward"]["twitch"]["reward_cost"],
                        minimum=1,
                    ),
                },
                "vk": {
                    "enabled": bool(vk_raw.get("enabled", False)),
                    "reward_id": MemeAlertsService._clean_optional_str(vk_raw.get("reward_id")),
                    "reward_title": MemeAlertsService._clean_optional_str(vk_raw.get("reward_title")),
                    "coins_amount": MemeAlertsService._safe_int(
                        vk_raw.get("coins_amount"),
                        DEFAULT_MEMEALERTS_SETTINGS["points_reward"]["vk"]["coins_amount"],
                        minimum=1,
                    ),
                    "reward_cost": MemeAlertsService._safe_int(
                        vk_raw.get("reward_cost"),
                        DEFAULT_MEMEALERTS_SETTINGS["points_reward"]["vk"]["reward_cost"],
                        minimum=1,
                    ),
                },
            },
            "points_rewards": [],
            "donation_auto": {
                "enabled": bool(donation_raw.get("enabled", False)),
                "coins_per_currency": MemeAlertsService._safe_float(
                    donation_raw.get("coins_per_currency"),
                    DEFAULT_MEMEALERTS_SETTINGS["donation_auto"]["coins_per_currency"],
                    minimum=0.01,
                ),
                "min_donation_amount": MemeAlertsService._safe_float(
                    donation_raw.get("min_donation_amount"),
                    DEFAULT_MEMEALERTS_SETTINGS["donation_auto"]["min_donation_amount"],
                    minimum=0.01,
                ),
            },
        }

        normalized_items: List[Dict[str, Any]] = []
        seen_local_ids: set[str] = set()
        for raw_item in points_rewards_raw:
            if not isinstance(raw_item, dict):
                continue
            item = MemeAlertsService._normalize_reward_item(raw_item)
            if item["local_id"] in seen_local_ids:
                item["local_id"] = uuid.uuid4().hex
            seen_local_ids.add(item["local_id"])
            normalized_items.append(item)
            if len(normalized_items) >= 3:
                break

        if not normalized_items:
            for platform in ("twitch", "vk"):
                legacy_item = normalized["points_reward"][platform]
                if legacy_item.get("reward_id") or legacy_item.get("enabled"):
                    normalized_items.append(
                        MemeAlertsService._normalize_reward_item(
                            {**legacy_item, "platform": platform},
                            platform,
                        )
                    )
                if len(normalized_items) >= 3:
                    break

        normalized["points_rewards"] = normalized_items
        MemeAlertsService._sync_legacy_points_reward(normalized)
        return normalized

    def _read_settings_from_tts(self, user_id: int) -> Dict[str, Any]:
        tts_settings = self.tts_repo.get_or_create(user_id=user_id)
        youtube_settings = getattr(tts_settings, "youtube_settings", None) or {}
        raw = youtube_settings.get("memealerts_settings")
        return self._normalize_settings(raw)

    def get_settings(self, user_id: int) -> Dict[str, Any]:
        return self._read_settings_from_tts(user_id)

    def save_settings(self, user_id: int, patch: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        current = self._read_settings_from_tts(user_id)
        payload = patch if isinstance(patch, dict) else {}
        should_validate_donation_integration = False

        next_settings = self._normalize_settings(current)

        points_patch = payload.get("points_reward")
        if isinstance(points_patch, dict):
            for platform in ("twitch", "vk"):
                platform_patch = points_patch.get(platform)
                if not isinstance(platform_patch, dict):
                    continue
                platform_current = next_settings["points_reward"][platform]
                if "enabled" in platform_patch:
                    platform_current["enabled"] = bool(platform_patch.get("enabled"))
                if "reward_id" in platform_patch:
                    platform_current["reward_id"] = self._clean_optional_str(platform_patch.get("reward_id"))
                if "reward_title" in platform_patch:
                    platform_current["reward_title"] = self._clean_optional_str(platform_patch.get("reward_title"))
                if "coins_amount" in platform_patch:
                    platform_current["coins_amount"] = self._safe_int(
                        platform_patch.get("coins_amount"),
                        platform_current["coins_amount"],
                        minimum=1,
                    )
                if "reward_cost" in platform_patch:
                    platform_current["reward_cost"] = self._safe_int(
                        platform_patch.get("reward_cost"),
                        platform_current["reward_cost"],
                        minimum=1,
                    )

        points_rewards_patch = payload.get("points_rewards")
        if isinstance(points_rewards_patch, list):
            normalized_items: List[Dict[str, Any]] = []
            seen_local_ids: set[str] = set()
            for raw_item in points_rewards_patch:
                if not isinstance(raw_item, dict):
                    continue
                item = self._normalize_reward_item(raw_item)
                if item["local_id"] in seen_local_ids:
                    item["local_id"] = uuid.uuid4().hex
                seen_local_ids.add(item["local_id"])
                normalized_items.append(item)
                if len(normalized_items) >= 3:
                    break
            next_settings["points_rewards"] = normalized_items

        donation_patch = payload.get("donation_auto")
        if isinstance(donation_patch, dict):
            donation_current = next_settings["donation_auto"]
            if "enabled" in donation_patch:
                donation_current["enabled"] = bool(donation_patch.get("enabled"))
                if donation_current["enabled"]:
                    should_validate_donation_integration = True
            if "coins_per_currency" in donation_patch:
                donation_current["coins_per_currency"] = self._safe_float(
                    donation_patch.get("coins_per_currency"),
                    donation_current["coins_per_currency"],
                    minimum=0.01,
                )
            if "min_donation_amount" in donation_patch:
                donation_current["min_donation_amount"] = self._safe_float(
                    donation_patch.get("min_donation_amount"),
                    donation_current["min_donation_amount"],
                    minimum=0.01,
                )

        if should_validate_donation_integration:
            da_token = self.token_repo.get_active_token(user_id, "donationalerts") or self.token_repo.get_by_user_and_platform(
                user_id, "donationalerts"
            )
            if not da_token or not da_token.access_token:
                raise ValueError("DonationAlerts integration must be connected before enabling auto grants")

        self._sync_legacy_points_reward(next_settings)
        tts_settings = self.tts_repo.get_or_create(user_id=user_id)
        youtube_settings = dict(getattr(tts_settings, "youtube_settings", None) or {})
        youtube_settings["memealerts_settings"] = next_settings
        self.tts_repo.update_settings(tts_settings, {"youtube_settings": youtube_settings})
        return next_settings

    @staticmethod
    def _build_platform_reward_payload(
        normalized_platform: str,
        reward_title: str,
        reward_cost: int,
        reward_cooldown: int,
    ) -> Dict[str, Any]:
        if normalized_platform == "twitch":
            return {
                "title": reward_title,
                "cost": reward_cost,
                "is_user_input_required": True,
                "prompt": "Введите ник MemeAlerts, которому выдать мемкоины",
                "global_cooldown_seconds": reward_cooldown,
                "is_global_cooldown_enabled": reward_cooldown > 0,
                "should_redemptions_skip_request_queue": False,
            }
        return {
            "name": reward_title,
            "description": "Введите ник MemeAlerts, которому выдать мемкоины",
            "price": reward_cost,
            "is_message_required": True,
            "repair_timeout": reward_cooldown,
        }

    def _find_reward_item(self, settings: Dict[str, Any], local_id: Optional[str]) -> Optional[Dict[str, Any]]:
        normalized_id = self._clean_optional_str(local_id)
        if not normalized_id:
            return None
        for item in settings.get("points_rewards", []):
            if isinstance(item, dict) and item.get("local_id") == normalized_id:
                return item
        return None

    @staticmethod
    def _reward_accepts_message(platform: str, reward: Dict[str, Any]) -> bool:
        if platform == "twitch":
            return reward.get("is_user_input_required") is True
        if platform == "vk":
            return reward.get("is_message_required") is True
        return False

    async def create_points_reward(
        self,
        *,
        user_id: int,
        platform: str,
        title: str,
        cost: int,
        coins_amount: int,
        cooldown_seconds: int = 0,
        local_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized_platform = (platform or "").strip().lower()
        if normalized_platform not in ("twitch", "vk"):
            raise ValueError("Unsupported platform")

        token = self.token_repo.get_active_token(user_id, normalized_platform) or self.token_repo.get_by_user_and_platform(
            user_id, normalized_platform
        )
        if not token or not token.access_token:
            raise ValueError(f"{normalized_platform} integration is not connected")

        reward_title = (title or "").strip() or "MemeCoins"
        reward_cost = self._safe_int(cost, 500, minimum=1)
        reward_coins = self._safe_int(coins_amount, 10, minimum=1)
        reward_cooldown = self._safe_int(cooldown_seconds, 0, minimum=0)

        from platforms.registry import platform_registry

        platform_impl = platform_registry.get(normalized_platform)
        if not platform_impl:
            raise RuntimeError(f"Platform {normalized_platform} is not initialized")

        settings = self.get_settings(user_id)
        items = list(settings.get("points_rewards", []))
        existing_item = self._find_reward_item(settings, local_id)
        reward_payload = self._build_platform_reward_payload(
            normalized_platform,
            reward_title,
            reward_cost,
            reward_cooldown,
        )

        if existing_item and existing_item.get("reward_id"):
            updated = await platform_impl.update_reward(user_id, str(existing_item["reward_id"]), reward_payload)
            if not updated:
                raise RuntimeError("Failed to update reward on platform")
            reward_id = str(existing_item["reward_id"])
            local_reward_id = str(existing_item["local_id"])
        else:
            if len(items) >= 3:
                raise ValueError("Можно создать не больше 3 наград MemeAlerts")
            reward_id = await platform_impl.create_reward(user_id, reward_payload)
            if not reward_id:
                raise RuntimeError("Failed to create reward on platform")
            local_reward_id = self._clean_optional_str(local_id) or uuid.uuid4().hex

        next_item = {
            "local_id": local_reward_id,
            "platform": normalized_platform,
            "enabled": True,
            "reward_id": str(reward_id),
            "reward_title": reward_title,
            "coins_amount": reward_coins,
            "reward_cost": reward_cost,
            "cooldown_seconds": reward_cooldown,
        }
        replaced = False
        next_items: List[Dict[str, Any]] = []
        for item in items:
            if isinstance(item, dict) and item.get("local_id") == local_reward_id:
                next_items.append(next_item)
                replaced = True
            else:
                next_items.append(item)
        if not replaced:
            next_items.append(next_item)

        settings = self.save_settings(user_id, {"points_rewards": next_items})
        return {
            "platform": normalized_platform,
            "reward_id": str(reward_id),
            "reward_title": reward_title,
            "coins_amount": reward_coins,
            "reward_cost": reward_cost,
            "local_id": local_reward_id,
            "settings": next_item,
            "all_settings": settings,
        }

    async def attach_points_reward(
        self,
        *,
        user_id: int,
        platform: str,
        reward_id: str,
        coins_amount: int,
        local_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized_platform = (platform or "").strip().lower()
        if normalized_platform not in ("twitch", "vk"):
            raise ValueError("Unsupported platform")

        normalized_reward_id = self._clean_optional_str(reward_id)
        if not normalized_reward_id:
            raise ValueError("Reward id is required")

        from services.platform_rewards_service import get_platform_rewards_service

        rewards = await get_platform_rewards_service().get_rewards(user_id, normalized_platform, self.db)
        reward = next((item for item in rewards if str(item.get("id")) == normalized_reward_id), None)
        if not reward:
            raise ValueError("Reward not found")
        if not self._reward_accepts_message(normalized_platform, reward):
            raise ValueError("MemeAlerts requires a reward with user message input enabled")

        settings = self.get_settings(user_id)
        items = list(settings.get("points_rewards", []))
        existing_item = self._find_reward_item(settings, local_id)
        if not existing_item and len(items) >= 3:
            raise ValueError("РњРѕР¶РЅРѕ СЃРѕР·РґР°С‚СЊ РЅРµ Р±РѕР»СЊС€Рµ 3 РЅР°РіСЂР°Рґ MemeAlerts")

        reward_title = self._clean_optional_str(reward.get("title")) or self._clean_optional_str(reward.get("name")) or "MemeCoins"
        reward_cost = self._safe_int(reward.get("cost", reward.get("price")), 500, minimum=1)
        reward_coins = self._safe_int(coins_amount, 10, minimum=1)
        local_reward_id = (
            self._clean_optional_str(local_id)
            or self._clean_optional_str(existing_item.get("local_id") if existing_item else None)
            or uuid.uuid4().hex
        )

        next_item = {
            "local_id": local_reward_id,
            "platform": normalized_platform,
            "enabled": True,
            "reward_id": normalized_reward_id,
            "reward_title": reward_title,
            "coins_amount": reward_coins,
            "reward_cost": reward_cost,
            "cooldown_seconds": self._safe_int(reward.get("global_cooldown_seconds"), 0, minimum=0, maximum=86_400),
        }
        replaced = False
        next_items: List[Dict[str, Any]] = []
        for item in items:
            if isinstance(item, dict) and item.get("local_id") == local_reward_id:
                next_items.append(next_item)
                replaced = True
            else:
                next_items.append(item)
        if not replaced:
            next_items.append(next_item)

        settings = self.save_settings(user_id, {"points_rewards": next_items})
        return {
            "platform": normalized_platform,
            "reward_id": normalized_reward_id,
            "reward_title": reward_title,
            "coins_amount": reward_coins,
            "reward_cost": reward_cost,
            "local_id": local_reward_id,
            "settings": next_item,
            "all_settings": settings,
        }

    async def update_points_reward_enabled(self, *, user_id: int, local_id: str, enabled: bool) -> Dict[str, Any]:
        settings = self.get_settings(user_id)
        items = list(settings.get("points_rewards", []))
        found = False
        for item in items:
            if isinstance(item, dict) and item.get("local_id") == local_id:
                item["enabled"] = bool(enabled)
                found = True
                break
        if not found:
            raise ValueError("Reward not found")
        return self.save_settings(user_id, {"points_rewards": items})

    async def delete_points_reward(self, *, user_id: int, local_id: str) -> Dict[str, Any]:
        settings = self.get_settings(user_id)
        items = list(settings.get("points_rewards", []))
        target = self._find_reward_item(settings, local_id)
        if not target:
            raise ValueError("Reward not found")

        reward_id = self._clean_optional_str(target.get("reward_id"))
        platform = str(target.get("platform") or "").strip().lower()
        if reward_id and platform in ("twitch", "vk"):
            from platforms.registry import platform_registry

            platform_impl = platform_registry.get(platform)
            if platform_impl:
                deleted = await platform_impl.delete_reward(user_id, reward_id)
                if not deleted:
                    raise RuntimeError("Failed to delete reward on platform")

        next_items = [item for item in items if not (isinstance(item, dict) and item.get("local_id") == local_id)]
        return self.save_settings(user_id, {"points_rewards": next_items})

    @staticmethod
    def _extract_supporter_nickname(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        first_line = text.splitlines()[0].strip()
        if not first_line:
            return None
        first_token = first_line.split()[0].strip().lstrip("@")
        return first_token or None

    async def process_points_reward_redemption(
        self,
        *,
        user_id: int,
        platform: str,
        channel_name: str,
        redeemer_name: str,
        reward_input: Optional[str],
        reward_id: Optional[str] = None,
        reward_title: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized_platform = (platform or "").strip().lower()
        if normalized_platform not in ("twitch", "vk"):
            return {"handled": False}

        settings = self.get_settings(user_id)
        platform_rewards = [
            item
            for item in settings.get("points_rewards", [])
            if isinstance(item, dict)
            and item.get("platform") == normalized_platform
            and item.get("enabled")
        ]
        if not platform_rewards:
            return {"handled": False}

        platform_settings = None
        if normalized_platform == "twitch":
            incoming_reward_id = self._clean_optional_str(reward_id)
            for item in platform_rewards:
                configured_reward_id = self._clean_optional_str(item.get("reward_id"))
                if configured_reward_id and incoming_reward_id and configured_reward_id == incoming_reward_id:
                    platform_settings = item
                    break
        else:
            incoming_title = (reward_title or "").strip().lower()
            for item in platform_rewards:
                configured_title = (item.get("reward_title") or "").strip().lower()
                if configured_title and incoming_title and configured_title == incoming_title:
                    platform_settings = item
                    break

        if not platform_settings:
            return {"handled": False}

        nickname = self._extract_supporter_nickname(reward_input)
        if not nickname:
            return {
                "handled": True,
                "success": False,
                "error": "Укажите ник MemeAlerts в сообщении награды",
            }

        coins_amount = self._safe_int(platform_settings.get("coins_amount"), 0, minimum=0)
        if coins_amount <= 0:
            return {
                "handled": True,
                "success": False,
                "error": "Некорректное количество мемкоинов в настройках награды",
            }

        result = await self.grant_coins(
            user_id=user_id,
            nickname_or_id=nickname,
            amount=coins_amount,
            platform=normalized_platform,
            channel_name=channel_name,
            issued_by=f"{redeemer_name}",
            source="points_reward",
        )
        if not result.get("success"):
            return {
                "handled": True,
                "success": False,
                "error": result.get("error"),
                "detail": result.get("detail"),
            }

        return {
            "handled": True,
            "success": True,
            "nickname": nickname,
            "amount": coins_amount,
            "data": result,
        }

    async def process_donation_auto_grant(
        self,
        *,
        user_id: int,
        channel_name: str,
        donor_name: Optional[str],
        donation_amount: Any,
    ) -> Dict[str, Any]:
        settings = self.get_settings(user_id)
        donation_settings = settings["donation_auto"]
        if not donation_settings.get("enabled"):
            return {"handled": False}

        da_token = self.token_repo.get_active_token(user_id, "donationalerts") or self.token_repo.get_by_user_and_platform(
            user_id, "donationalerts"
        )
        if not da_token or not da_token.access_token:
            return {
                "handled": True,
                "success": False,
                "error": "DonationAlerts не подключен",
            }

        nickname = self._extract_supporter_nickname(donor_name)
        if not nickname:
            return {
                "handled": True,
                "success": False,
                "error": "В донате нет ника для выдачи",
            }

        amount_value = self._safe_float(donation_amount, 0.0, minimum=0.0)
        min_donation = self._safe_float(donation_settings.get("min_donation_amount"), 1.0, minimum=0.01)
        if amount_value < min_donation:
            return {
                "handled": True,
                "success": False,
                "error": "Донат меньше минимального порога",
            }

        coins_per_currency = self._safe_float(donation_settings.get("coins_per_currency"), 1.0, minimum=0.01)
        coins_amount = int(round(amount_value * coins_per_currency))
        if coins_amount <= 0:
            return {
                "handled": True,
                "success": False,
                "error": "По текущему курсу получается 0 мемкоинов",
            }

        result = await self.grant_coins(
            user_id=user_id,
            nickname_or_id=nickname,
            amount=coins_amount,
            platform="donationalerts",
            channel_name=channel_name,
            issued_by=nickname,
            source="donation_auto",
        )

        if not result.get("success"):
            return {
                "handled": True,
                "success": False,
                "error": result.get("error"),
                "detail": result.get("detail"),
            }

        return {
            "handled": True,
            "success": True,
            "nickname": nickname,
            "amount": coins_amount,
            "data": result,
        }

    def _get_token(self, user_id: int) -> Tuple[str, Optional[str]]:
        from core.token_encryption import decrypt_token

        token = self.token_repo.get_by_user_and_platform(user_id, "memealerts")
        if not token or not token.access_token:
            raise ValueError("MemeAlerts not connected")
        return decrypt_token(token.access_token), token.platform_user_id

    @staticmethod
    def _decode_token(token: str) -> Dict[str, Any]:
        try:
            return jwt.decode(token, options={"verify_signature": False})
        except jwt.PyJWTError:
            return {}

    @staticmethod
    def _resolve_streamer_id(decoded: Dict[str, Any], platform_user_id: Optional[str]) -> Optional[str]:
        return (
            decoded.get("streamer_id")
            or decoded.get("streamerId")
            or decoded.get("id")
            or decoded.get("_id")
            or decoded.get("user_id")
            or decoded.get("uid")
            or decoded.get("sub")
            or platform_user_id
            or decoded.get("tid")
        )

    @staticmethod
    def _safe_iso(value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, datetime):
            try:
                normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
                return normalized.astimezone(timezone.utc).isoformat()
            except Exception:
                return str(value)
        if hasattr(value, "isoformat"):
            try:
                return value.isoformat()
            except Exception:
                return str(value)
        return str(value)

    def _read_local_grants(self, user_id: int, limit: int) -> List[Dict[str, Any]]:
        rows = (
            self.db.query(MemeAlertsGrantHistory)
            .filter(MemeAlertsGrantHistory.user_id == user_id)
            .order_by(
                MemeAlertsGrantHistory.created_at.desc(),
                MemeAlertsGrantHistory.id.desc(),
            )
            .limit(limit)
            .all()
        )

        return [
            {
                "id": row.id,
                "type": row.source or "ui",
                "amount": row.amount,
                "user_id": row.target_user_id,
                "user_name": row.target_user_name,
                "memealerts_name": row.target_user_name,
                "platform": row.platform,
                "platform_user_name": row.issued_by,
                "source": row.source,
                "channel_name": row.channel_name,
                "created_at": self._safe_iso(row.created_at),
            }
            for row in rows
        ]

    def _record_local_grant(
        self,
        *,
        user_id: int,
        target_user_id: Optional[str],
        target_user_name: Optional[str],
        amount: int,
        source: str,
        platform: str,
        channel_name: str,
        issued_by: str,
    ) -> None:
        try:
            self.db.add(
                MemeAlertsGrantHistory(
                    user_id=user_id,
                    target_user_id=target_user_id,
                    target_user_name=target_user_name,
                    amount=amount,
                    source=source,
                    platform=platform,
                    channel_name=channel_name,
                    issued_by=issued_by,
                )
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            logger.warning(
                "Failed to persist MemeAlerts local grant history", exc_info=True
            )

    async def _request(
        self,
        method: str,
        endpoint: str,
        access_token: str,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        *,
        client: Optional[httpx.AsyncClient] = None,
    ) -> httpx.Response:
        url = f"{MEMEALERTS_API_BASE}{endpoint}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            **MEMEALERTS_BROWSER_HEADERS,
        }

        if client is not None:
            return await client.request(
                method, url, params=params, json=json, headers=headers
            )

        async with httpx.AsyncClient(timeout=30.0) as local_client:
            return await local_client.request(
                method, url, params=params, json=json, headers=headers
            )

    async def validate_access_token(self, access_token: str, streamer_id: str) -> Dict[str, Any]:
        """Validate a MemeAlerts token with a read-only API call before storing it."""
        normalized_streamer_id = self._clean_optional_str(streamer_id)
        if not access_token or not normalized_streamer_id:
            raise ValueError("MemeAlerts token validation requires a streamer id")

        token_only_response = await self._request(
            "POST",
            "/supporters",
            access_token,
            json={"limit": 1, "skip": 0, "query": ""},
        )
        if token_only_response.status_code in (200, 201):
            logger.info(
                "MemeAlerts token validated via token-only supporters request for streamer_id=%s",
                normalized_streamer_id,
            )
            return {"streamer_id": normalized_streamer_id}

        if token_only_response.status_code in (401, 403):
            raise ValueError("MemeAlerts token validation failed")

        response = await self._request(
            "POST",
            "/supporters",
            access_token,
            json={
                "streamerId": normalized_streamer_id,
                "limit": 1,
                "skip": 0,
                "query": "",
                "filters": [],
            },
        )
        if response.status_code in (200, 201):
            return {"streamer_id": normalized_streamer_id}

        if response.status_code in (401, 403):
            raise ValueError("MemeAlerts token validation failed")

        logger.warning(
            "MemeAlerts token validation unavailable: streamer_status=%s streamer_body=%s token_status=%s token_body=%s",
            response.status_code,
            response.text[:500],
            token_only_response.status_code,
            token_only_response.text[:500],
        )
        raise RuntimeError("MemeAlerts token validation is temporarily unavailable")

    @staticmethod
    def _has_antibot_cookie(response: httpx.Response) -> bool:
        return any(
            "__ddg" in cookie.lower()
            for cookie in response.headers.get_list("set-cookie")
        )

    @staticmethod
    def _extract_user_id(payload: Any) -> Optional[str]:
        if isinstance(payload, dict):
            for key in ("supporterId", "supporter_id", "_id", "id", "userId", "uid"):
                value = payload.get(key)
                if value:
                    return str(value)

            for key in ("user", "data", "result", "item"):
                nested = payload.get(key)
                user_id = MemeAlertsService._extract_user_id(nested)
                if user_id:
                    return user_id

            for key in ("items", "users", "results", "list"):
                nested = payload.get(key)
                user_id = MemeAlertsService._extract_user_id(nested)
                if user_id:
                    return user_id

        if isinstance(payload, list):
            for item in payload:
                user_id = MemeAlertsService._extract_user_id(item)
                if user_id:
                    return user_id

        return None

    @staticmethod
    def _extract_name_candidates(payload: Any) -> List[str]:
        if not isinstance(payload, dict):
            return []

        candidates: List[str] = []
        for key in (
            "supporterName",
            "userName",
            "nickname",
            "name",
            "username",
            "login",
            "displayName",
            "userAlias",
        ):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                candidates.append(value.strip())

        nested_user = payload.get("user")
        if isinstance(nested_user, dict):
            candidates.extend(MemeAlertsService._extract_name_candidates(nested_user))

        return candidates

    async def _resolve_user_id_via_supporters(
        self,
        access_token: str,
        streamer_id: str,
        nickname: str,
        *,
        client: Optional[httpx.AsyncClient] = None,
    ) -> Optional[str]:
        normalized = nickname.strip().lstrip("@").lower()
        if not normalized:
            return None

        limit = 100
        skip = 0
        max_pages = 30

        for _ in range(max_pages):
            payload_variants = [
                {
                    "limit": limit,
                    "skip": skip,
                    "query": nickname,
                },
                {
                    "limit": limit,
                    "skip": skip,
                    "query": nickname,
                    "filters": [],
                },
                {
                    "limit": limit,
                    "skip": skip,
                    "query": "",
                },
                {
                    "limit": limit,
                    "skip": skip,
                    "query": "",
                    "filters": [],
                },
                {
                    "streamerId": streamer_id,
                    "limit": limit,
                    "skip": skip,
                    "query": nickname,
                    "filters": [],
                },
                {
                    "streamerId": streamer_id,
                    "limit": limit,
                    "skip": skip,
                    "query": "",
                    "filters": [],
                },
            ]

            response_payload: Any = None
            supporters: List[Dict[str, Any]] = []

            for payload in payload_variants:
                response: Optional[httpx.Response] = None

                for attempt in range(2):
                    response = await self._request(
                        "POST",
                        "/supporters",
                        access_token,
                        json=payload,
                        client=client,
                    )
                    if response.status_code in (200, 201):
                        break
                    if attempt == 0 and self._has_antibot_cookie(response):
                        logger.info(
                            "MemeAlerts supporters scan anti-bot challenge detected, retrying once"
                        )
                        continue
                    break

                if response is None or response.status_code not in (200, 201):
                    logger.debug(
                        "MemeAlerts supporters scan variant failed: status=%s has_streamer_id=%s has_query=%s",
                        response.status_code if response else None,
                        bool(payload.get("streamerId")),
                        bool(payload.get("query")),
                    )
                    continue

                raw_body = (response.text or "").strip()
                if not raw_body:
                    logger.debug(
                        "MemeAlerts supporters scan variant returned empty body: has_streamer_id=%s has_query=%s",
                        bool(payload.get("streamerId")),
                        bool(payload.get("query")),
                    )
                    continue

                try:
                    response_payload = response.json()
                except Exception:
                    logger.exception("MemeAlerts supporters scan JSON decode failed")
                    continue

                extracted = self._extract_list(response_payload)
                if extracted:
                    supporters = [item for item in extracted if isinstance(item, dict)]
                    if supporters:
                        break

            if not supporters:
                return None

            for supporter in supporters:
                if not isinstance(supporter, dict):
                    continue
                names = self._extract_name_candidates(supporter)
                is_match = any(
                    name.strip().lstrip("@").lower() == normalized for name in names
                )
                if not is_match:
                    continue

                supporter_id = self._extract_user_id(supporter)
                if supporter_id:
                    logger.info(
                        f"MemeAlerts supporters scan matched nickname={nickname}, user_id={supporter_id}"
                    )
                    return supporter_id

            total = None
            if isinstance(response_payload, dict):
                total_value = response_payload.get("total")
                if isinstance(total_value, int):
                    total = total_value

            consumed = len(supporters)
            if consumed <= 0:
                return None

            skip += consumed
            if total is not None and skip >= total:
                break
            if consumed < limit:
                break

        return None

    async def _resolve_user_id_via_streamer_lookup(
        self,
        access_token: str,
        nickname: str,
        *,
        client: Optional[httpx.AsyncClient] = None,
    ) -> Optional[str]:
        normalized = nickname.strip().lstrip("@").lower()
        if not normalized:
            return None

        payload = {"value": nickname}
        for attempt in range(2):
            try:
                response = await self._request(
                    "POST",
                    "/user/find/streamer",
                    access_token,
                    json=payload,
                    client=client,
                )
            except Exception:
                logger.exception("MemeAlerts streamer lookup failed")
                return None

            if response.status_code not in (200, 201):
                if attempt == 0 and self._has_antibot_cookie(response):
                    logger.info(
                        "MemeAlerts streamer lookup anti-bot challenge detected, retrying once: "
                        f"payload={payload}"
                    )
                    continue
                return None

            raw_body = (response.text or "").strip()
            if not raw_body:
                if attempt == 0 and self._has_antibot_cookie(response):
                    continue
                return None

            try:
                response_payload = response.json()
            except Exception:
                logger.exception("MemeAlerts streamer lookup JSON decode failed")
                return None

            streamers = self._extract_list(response_payload)
            if not streamers:
                return None

            for streamer in streamers:
                if not isinstance(streamer, dict):
                    continue

                names = self._extract_name_candidates(streamer)
                channel = streamer.get("channel")
                if isinstance(channel, dict):
                    names.extend(self._extract_name_candidates(channel))

                is_match = any(
                    name.strip().lstrip("@").lower() == normalized for name in names
                )
                if not is_match:
                    continue

                streamer_user_id = self._extract_user_id(streamer)
                if streamer_user_id:
                    logger.info(
                        "MemeAlerts streamer lookup matched nickname=%s, user_id=%s",
                        nickname,
                        streamer_user_id,
                    )
                    return streamer_user_id

            if len(streamers) == 1:
                single_id = self._extract_user_id(streamers[0])
                if single_id:
                    logger.info(
                        "MemeAlerts streamer lookup returned single candidate nickname=%s, user_id=%s",
                        nickname,
                        single_id,
                    )
                    return single_id

            return None

        return None

    async def _resolve_user_id(
        self,
        access_token: str,
        nickname_or_id: str,
        streamer_id: Optional[str] = None,
        *,
        client: Optional[httpx.AsyncClient] = None,
    ) -> Optional[str]:
        if nickname_or_id.isdigit():
            return nickname_or_id
        if MEMEALERTS_OBJECT_ID_RE.fullmatch(nickname_or_id):
            return nickname_or_id

        nickname = nickname_or_id.lstrip("@")
        if not nickname:
            return None

        if streamer_id:
            supporter_id = await self._resolve_user_id_via_supporters(
                access_token,
                streamer_id=str(streamer_id),
                nickname=nickname,
                client=client,
            )
            if supporter_id:
                return supporter_id

        return None

    async def grant_coins(
        self,
        user_id: int,
        nickname_or_id: str,
        amount: int,
        *,
        platform: str,
        channel_name: str,
        issued_by: str,
        source: str = "command",
    ) -> Dict[str, Any]:
        try:
            access_token, platform_user_id = self._get_token(user_id)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        decoded = self._decode_token(access_token)
        streamer_id = self._resolve_streamer_id(decoded, platform_user_id)

        if not streamer_id:
            return {"success": False, "error": "Streamer ID not found in token"}

        async with httpx.AsyncClient(timeout=30.0) as shared_client:
            target_user_id = await self._resolve_user_id(
                access_token,
                nickname_or_id,
                streamer_id=str(streamer_id),
                client=shared_client,
            )
            if not target_user_id:
                return {
                    "success": False,
                    "error": "Пользователь MemeAlerts не найден",
                    "detail": (
                        "Укажите nickname пользователя, который уже есть в MemeAlerts supporters. "
                        "Twitch/VK ник может не совпадать с MemeAlerts."
                    ),
                }

            payload = {
                "userId": target_user_id,
                "streamerId": streamer_id,
                "value": int(amount),
            }

            response: Optional[httpx.Response] = None
            for attempt in range(2):
                response = await self._request(
                    "POST",
                    "/user/give-bonus",
                    access_token,
                    json=payload,
                    client=shared_client,
                )
                if response.status_code in (200, 201):
                    break
                if attempt == 0 and self._has_antibot_cookie(response):
                    logger.info(
                        "MemeAlerts give-bonus anti-bot challenge detected, retrying once"
                    )
                    continue
                break

            if response is None or response.status_code not in (200, 201):
                status_code = response.status_code if response else None
                detail = response.text if response else None
                error_message = f"API Error: {status_code if status_code is not None else 'unknown'}"
                if status_code in (401, 403, 404):
                    error_message = "Пользователь не найден в MemeAlerts supporters или недоступен для выдачи"
                logger.warning(
                    "MemeAlerts give-bonus failed: status=%s target_resolved=%s streamer_id_present=%s body=%s",
                    status_code,
                    bool(target_user_id),
                    bool(streamer_id),
                    (detail or "")[:500],
                )
                return {
                    "success": False,
                    "error": (
                        "Пользователь не найден в MemeAlerts supporters или недоступен для выдачи"
                        if status_code in (401, 403, 404)
                        else error_message
                    ),
                    "detail": detail,
                    "status_code": status_code,
                }

            response_data: Dict[str, Any] = {}
            raw_body = (response.text or "").strip()
            if raw_body:
                try:
                    parsed_data = response.json()
                    if isinstance(parsed_data, dict):
                        response_data = parsed_data
                    else:
                        response_data = {"raw": parsed_data}
                except Exception:
                    response_data = {"raw": raw_body}

        target_name = nickname_or_id.strip()
        if target_name.isdigit() or MEMEALERTS_OBJECT_ID_RE.fullmatch(target_name):
            target_name = ""
        self._record_local_grant(
            user_id=user_id,
            target_user_id=str(target_user_id) if target_user_id else None,
            target_user_name=target_name or None,
            amount=int(amount),
            source=source,
            platform=platform,
            channel_name=channel_name,
            issued_by=issued_by,
        )

        return {
            "success": True,
            "target_user_id": target_user_id,
            "nickname": nickname_or_id,
            "amount": amount,
            "source": source,
            "platform": platform,
            "channel_name": channel_name,
            "issued_by": issued_by,
            "data": response_data,
        }

    async def fetch_history(self, user_id: int, limit: int = 50) -> Dict[str, Any]:
        try:
            access_token, platform_user_id = self._get_token(user_id)
        except ValueError as exc:
            return {
                "success": False,
                "error": str(exc),
                "history": [],
                "local_grants": [],
                "grants": [],
                "purchases": [],
                "unknown": [],
            }

        grants = self._read_local_grants(user_id=user_id, limit=limit)
        decoded = self._decode_token(access_token)
        streamer_id = self._resolve_streamer_id(decoded, platform_user_id)
        remote_history: List[Dict[str, Any]] = []

        if not streamer_id:
            logger.warning(
                "MemeAlerts history: streamer_id is missing, purchases list will be empty"
            )
        else:
            async with httpx.AsyncClient(timeout=30.0) as shared_client:
                supporters = await self._fetch_supporters(
                    access_token=access_token,
                    streamer_id=str(streamer_id),
                    limit=limit,
                    client=shared_client,
                )
            remote_history = self._normalize_supporters(supporters)

        return {
            "success": True,
            "history": remote_history,
            "local_grants": grants,
            "grants": grants,
            "purchases": remote_history,
            "unknown": [],
            "source": "memealerts_supporters",
        }

    async def fetch_balances(self, user_id: int, limit: int = 200) -> Dict[str, Any]:
        try:
            access_token, platform_user_id = self._get_token(user_id)
        except ValueError as exc:
            return {
                "success": False,
                "error": str(exc),
                "balances": [],
                "source": "memealerts_supporters",
            }

        decoded = self._decode_token(access_token)
        streamer_id = self._resolve_streamer_id(decoded, platform_user_id)
        if not streamer_id:
            logger.warning("MemeAlerts balances: streamer_id is missing")
            return {
                "success": True,
                "balances": [],
                "source": "memealerts_supporters",
            }

        async with httpx.AsyncClient(timeout=30.0) as shared_client:
            supporters = await self._fetch_supporters(
                access_token=access_token,
                streamer_id=str(streamer_id),
                limit=limit,
                client=shared_client,
            )

        return {
            "success": True,
            "balances": self._normalize_supporter_balances(supporters),
            "source": "memealerts_supporters",
        }

    async def _fetch_supporters(
        self,
        access_token: str,
        streamer_id: str,
        limit: int,
        *,
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[Dict[str, Any]]:
        if not streamer_id:
            return []

        supporters: List[Dict[str, Any]] = []
        skip = 0
        page_limit = 100
        max_pages = 30

        for _ in range(max_pages):
            remaining = limit - len(supporters)
            if remaining <= 0:
                break

            request_limit = min(page_limit, remaining)
            payload_variants = [
                {
                    "limit": request_limit,
                    "skip": skip,
                    "query": "",
                },
                {
                    "limit": request_limit,
                    "skip": skip,
                    "query": "",
                    "filters": [],
                },
                {
                    "streamerId": streamer_id,
                    "limit": request_limit,
                    "skip": skip,
                    "query": "",
                    "filters": [],
                },
            ]
            response: Optional[httpx.Response] = None

            for payload in payload_variants:
                for attempt in range(2):
                    try:
                        response = await self._request(
                            "POST",
                            "/supporters",
                            access_token,
                            json=payload,
                            client=client,
                        )
                    except Exception:
                        logger.exception("MemeAlerts supporters fetch failed")
                        response = None
                        break

                    if response.status_code in (200, 201):
                        break
                    if attempt == 0 and self._has_antibot_cookie(response):
                        continue
                    logger.debug(
                        "MemeAlerts supporters fetch variant failed with status=%s has_streamer_id=%s has_filters=%s",
                        response.status_code,
                        bool(payload.get("streamerId")),
                        "filters" in payload,
                    )
                    response = None
                    break

                if response is not None and response.status_code in (200, 201):
                    break

            if response is None:
                break

            raw_body = (response.text or "").strip()
            if not raw_body:
                if self._has_antibot_cookie(response):
                    continue
                logger.warning(
                    "MemeAlerts supporters endpoint returned empty body for payload=%s",
                    payload,
                )
                break

            try:
                response_payload = response.json()
            except Exception:
                logger.exception("MemeAlerts supporters JSON decode failed")
                break

            page_items = self._extract_list(response_payload)
            if not page_items:
                break

            supporters.extend([item for item in page_items if isinstance(item, dict)])

            total = None
            if isinstance(response_payload, dict):
                total_value = response_payload.get("total")
                if isinstance(total_value, int):
                    total = total_value

            consumed = len(page_items)
            if consumed <= 0:
                break

            skip += consumed
            if total is not None and skip >= total:
                break
            if consumed < request_limit:
                break

        return supporters[:limit]

    @staticmethod
    def _extract_list(payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("data", "items", "list", "history", "transactions", "results"):
                if isinstance(payload.get(key), list):
                    return payload.get(key)
            data = payload.get("data")
            if isinstance(data, dict):
                for key in ("items", "list", "history", "transactions"):
                    if isinstance(data.get(key), list):
                        return data.get(key)
        return []

    @staticmethod
    def _normalize_supporter_amount(item: Dict[str, Any]) -> Optional[float]:
        for key in ("amount", "sum", "total", "value", "purchased", "spent", "balance"):
            value = item.get(key)
            if value in (None, ""):
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _normalize_supporter_timestamp(item: Dict[str, Any]) -> Optional[str]:
        raw_value = (
            item.get("createdAt")
            or item.get("updatedAt")
            or item.get("date")
            or item.get("lastSupport")
            or item.get("joined")
        )
        if raw_value in (None, ""):
            return None

        if isinstance(raw_value, datetime):
            return raw_value.isoformat()

        if isinstance(raw_value, (int, float)):
            timestamp = float(raw_value)
            if timestamp > 1_000_000_000_000:
                timestamp /= 1000.0
            try:
                return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
            except (OSError, OverflowError, ValueError):
                return str(raw_value)

        if isinstance(raw_value, str):
            text = raw_value.strip()
            if not text:
                return None
            if text.isdigit():
                try:
                    timestamp = float(text)
                    if timestamp > 1_000_000_000_000:
                        timestamp /= 1000.0
                    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
                except (OSError, OverflowError, ValueError):
                    return text
            try:
                normalized_text = text.replace("Z", "+00:00")
                parsed = datetime.fromisoformat(normalized_text)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc).isoformat()
            except ValueError:
                return text

        return str(raw_value)

    @staticmethod
    def _extract_supporter_name(item: Dict[str, Any]) -> Optional[str]:
        user_info = item.get("user") if isinstance(item.get("user"), dict) else {}
        viewer_info = item.get("viewer") if isinstance(item.get("viewer"), dict) else {}
        channel_info = item.get("channel") if isinstance(item.get("channel"), dict) else {}
        return (
            item.get("supporterName")
            or item.get("userName")
            or item.get("nickname")
            or user_info.get("nickname")
            or viewer_info.get("nickname")
            or channel_info.get("name")
        )

    @staticmethod
    def _extract_supporter_balance(item: Dict[str, Any]) -> Optional[float]:
        for key in ("balance", "bonus", "memeCoins", "memecoins", "coins"):
            value = item.get(key)
            if value in (None, ""):
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _normalize_supporter_balances(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        balances: List[Dict[str, Any]] = []
        for item in items:
            user_info = item.get("user") if isinstance(item.get("user"), dict) else {}
            viewer_info = item.get("viewer") if isinstance(item.get("viewer"), dict) else {}
            supporter_id = (
                item.get("supporterId")
                or item.get("userId")
                or item.get("uid")
                or user_info.get("id")
                or viewer_info.get("id")
            )
            balances.append(
                {
                    "id": item.get("id") or item.get("_id") or supporter_id,
                    "user_id": supporter_id,
                    "memealerts_name": MemeAlertsService._extract_supporter_name(item),
                    "amount": MemeAlertsService._extract_supporter_balance(item),
                    "spent": MemeAlertsService._safe_float(item.get("spent"), 0.0),
                    "purchased": MemeAlertsService._safe_float(item.get("purchased"), 0.0),
                    "last_grant_at": MemeAlertsService._normalize_supporter_timestamp(item),
                    "source": "memealerts_supporters",
                }
            )
        return balances

    @staticmethod
    def _normalize_supporters(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        purchases: List[Dict[str, Any]] = []
        for item in items:
            user_info = item.get("user") if isinstance(item.get("user"), dict) else {}
            viewer_info = item.get("viewer") if isinstance(item.get("viewer"), dict) else {}
            user_name = MemeAlertsService._extract_supporter_name(item)
            purchases.append(
                {
                    "id": item.get("id") or item.get("_id"),
                    "type": item.get("type") or item.get("kind") or "purchase",
                    "amount": MemeAlertsService._normalize_supporter_amount(item),
                    "user_id": (
                        item.get("supporterId")
                        or item.get("userId")
                        or item.get("uid")
                        or user_info.get("id")
                        or viewer_info.get("id")
                    ),
                    "user_name": user_name,
                    "created_at": MemeAlertsService._normalize_supporter_timestamp(item),
                    "raw": item,
                }
            )
        return purchases

