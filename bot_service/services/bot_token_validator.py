"""
Validation and monitoring for dedicated bot OAuth tokens.

Runtime policy:
- Bot tokens are loaded from DB (`bot_tokens`) only.
- No legacy env token fallback.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional

import httpx

from core.config import settings
from core.database import db_session
from core.datetime_utils import utcnow_naive
from repositories.bot_token_repository import BotTokenRepository
from services.twitch_bot_oauth_service import twitch_bot_oauth_service

logger = logging.getLogger(__name__)


REQUIRED_TWITCH_CHAT_SCOPES = {"chat:read", "chat:edit"}
TWITCH_TOKEN_VALIDATE_RETRIES = 3


class BotTokenValidator:
    """Validation helpers for Twitch/VK bot OAuth tokens."""

    def __init__(self):
        self.last_twitch_check: Optional[datetime] = None
        self.last_vk_check: Optional[datetime] = None
        self.twitch_token_valid: bool = False
        self.vk_token_valid: bool = False
        self._monitoring_task: Optional[asyncio.Task] = None

    def _sync_twitch_bot_login(self, expected_login: Optional[str], actual_login: Optional[str]) -> None:
        normalized_actual = str(actual_login or "").strip().lower()
        normalized_expected = str(expected_login or "").strip().lower()
        if not normalized_actual or normalized_actual == normalized_expected:
            return

        try:
            with db_session() as db:
                repo = BotTokenRepository(db)
                bot_token = repo.get_by_platform("twitch")
                if not bot_token:
                    return

                bot_token.bot_login = normalized_actual
                bot_token.updated_at = utcnow_naive()
                repo.save(bot_token)
                logger.info(
                    "[BOT TOKEN] Synced stored Twitch bot login from %s to %s",
                    normalized_expected or "<empty>",
                    normalized_actual,
                )
        except Exception:
            logger.exception("[BOT TOKEN] Failed to sync Twitch bot login to validated identity")

    async def validate_twitch_bot_token(self) -> Dict[str, Any]:
        """Validate Twitch bot token from DB."""
        try:
            bot_token = await twitch_bot_oauth_service.get_bot_token()
        except Exception:
            logger.exception("[BOT TOKEN] Failed to get Twitch token from DB")
            bot_token = None

        token_to_check = bot_token.get("access_token") if bot_token else None
        if not token_to_check:
            self.twitch_token_valid = False
            return {
                "valid": False,
                "error": "Twitch bot token not configured",
                "instructions": (
                    "Authorize bot via /auth/twitch/bot/login "
                    "or generate one-time link via /api/admin/bot/twitch/login-link"
                ),
            }

        if token_to_check.startswith("oauth:"):
            token_to_check = token_to_check.split("oauth:", 1)[1]

        try:
            response = await self._request_twitch_token_validation(token_to_check)
        except httpx.TransportError as exc:
            logger.warning("[BOT TOKEN] Twitch token validation temporarily unavailable: %s", exc)
            return {
                "valid": False,
                "transient": True,
                "error": "Twitch token validation temporarily unavailable",
            }
        except Exception:
            logger.exception("[ERROR] [BOT TOKEN] Failed to validate Twitch token")
            return {"valid": False, "error": "Internal server error"}

        try:
            if response.status_code == 200:
                data = response.json()
                scopes = set(data.get("scopes", []))
                missing_chat_scopes = sorted(REQUIRED_TWITCH_CHAT_SCOPES - scopes)
                if missing_chat_scopes:
                    self.twitch_token_valid = False
                    logger.error(
                        "[ERROR] [BOT TOKEN] Twitch token is valid OAuth, but missing chat bot scopes: %s",
                        ", ".join(missing_chat_scopes),
                    )
                    return {
                        "valid": False,
                        "error": "Twitch bot token is missing required chat scopes",
                        "missing_scopes": missing_chat_scopes,
                        "scopes": sorted(scopes),
                        "instructions": (
                            "Re-authorize the dedicated Twitch bot via /auth/twitch/bot/login "
                            "or /api/admin/bot/twitch/login-link"
                        ),
                    }

                self.twitch_token_valid = True
                self.last_twitch_check = utcnow_naive()

                db_login = bot_token.get("bot_login") if bot_token else None
                validated_login = data.get("login")
                if db_login and validated_login != db_login:
                    logger.info(
                        "[BOT TOKEN] Twitch token belongs to %s, stored login was %s; updating DB",
                        validated_login,
                        db_login,
                    )
                    self._sync_twitch_bot_login(db_login, validated_login)

                logger.info("[OK] [BOT TOKEN] Twitch bot token is VALID")
                return {
                    "valid": True,
                    "user_id": data.get("user_id"),
                    "login": data.get("login"),
                    "expires_in": data.get("expires_in"),
                    "scopes": sorted(scopes),
                }

            if response.status_code == 401:
                self.twitch_token_valid = False
                logger.error("[ERROR] [BOT TOKEN] Twitch bot token is INVALID or EXPIRED")

                # Auto-refresh if DB refresh token exists.
                if bot_token and bot_token.get("refresh_token"):
                    logger.info("[BOT TOKEN] Attempting Twitch bot token refresh...")
                    refresh_success = await twitch_bot_oauth_service.refresh_bot_token()
                    if refresh_success:
                        logger.info("[BOT TOKEN] Refresh successful, re-validating...")
                        return await self.validate_twitch_bot_token()

                return {
                    "valid": False,
                    "error": "Token invalid or expired",
                    "status_code": 401,
                    "instructions": (
                        "Re-authorize Twitch bot via /auth/twitch/bot/login "
                        "or /api/admin/bot/twitch/login-link"
                    ),
                }

            logger.error(f"[ERROR] [BOT TOKEN] Unexpected Twitch response: {response.status_code}")
            return {
                "valid": False,
                "error": f"Unexpected status code: {response.status_code}",
                "status_code": response.status_code,
            }

        except Exception:
            logger.exception("[ERROR] [BOT TOKEN] Failed to validate Twitch token")
            return {"valid": False, "error": "Internal server error"}

    async def _request_twitch_token_validation(self, token_to_check: str) -> httpx.Response:
        last_error: Optional[httpx.TransportError] = None
        for attempt in range(1, TWITCH_TOKEN_VALIDATE_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    return await client.get(
                        "https://id.twitch.tv/oauth2/validate",
                        headers={"Authorization": f"Bearer {token_to_check}"},
                    )
            except httpx.TransportError as exc:
                last_error = exc
                logger.warning(
                    "[BOT TOKEN] Twitch token validation network error attempt %s/%s: %s",
                    attempt,
                    TWITCH_TOKEN_VALIDATE_RETRIES,
                    exc,
                )
                if attempt < TWITCH_TOKEN_VALIDATE_RETRIES:
                    await asyncio.sleep(min(attempt, 3))

        if last_error:
            raise last_error
        raise RuntimeError("Twitch token validation failed without a response")

    async def validate_vk_bot_token(self) -> Dict[str, Any]:
        """Validate VK bot token from DB."""
        from services.vk_bot_oauth_service import vk_bot_oauth_service

        try:
            bot_token = await vk_bot_oauth_service.get_bot_token()
        except Exception:
            logger.exception("[BOT TOKEN] Failed to get VK token from DB")
            bot_token = None

        token_to_check = bot_token.get("access_token") if bot_token else None
        if not token_to_check:
            self.vk_token_valid = False
            return {
                "valid": False,
                "error": "VK bot token not configured",
                "instructions": (
                    "Authorize VK bot via /auth/vk/bot/login "
                    "or generate one-time link via /api/admin/bot/vk/login-link"
                ),
            }

        try:
            ssl_verify = settings.is_production
            async with httpx.AsyncClient(timeout=10.0, verify=ssl_verify) as client:
                response = await client.get(
                    "https://apidev.live.vkvideo.ru/v1/current_user",
                    headers={"Authorization": f"Bearer {token_to_check}"},
                )

            if response.status_code == 200:
                data = response.json()
                user_data = data.get("data", {}).get("user", {})

                self.vk_token_valid = True
                self.last_vk_check = utcnow_naive()
                logger.info("[OK] [BOT TOKEN] VK bot token is VALID")
                return {
                    "valid": True,
                    "username": user_data.get("nick"),
                    "user_id": user_data.get("id"),
                    "type": "user_token",
                }

            if response.status_code == 401:
                self.vk_token_valid = False
                logger.error("[ERROR] [BOT TOKEN] VK bot token is INVALID or EXPIRED")

                if bot_token and bot_token.get("refresh_token"):
                    logger.info("[BOT TOKEN] Attempting VK bot token refresh...")
                    refresh_success = await vk_bot_oauth_service.refresh_bot_token()
                    if refresh_success:
                        logger.info("[BOT TOKEN] Refresh successful, re-validating...")
                        return await self.validate_vk_bot_token()

                return {
                    "valid": False,
                    "error": "Token invalid or expired",
                    "status_code": 401,
                    "instructions": (
                        "Re-authorize VK bot via /auth/vk/bot/login "
                        "or /api/admin/bot/vk/login-link"
                    ),
                }

            logger.error(f"[ERROR] [BOT TOKEN] Unexpected VK response: {response.status_code}")
            return {
                "valid": False,
                "error": f"Unexpected status code: {response.status_code}",
                "status_code": response.status_code,
            }

        except Exception:
            logger.exception("[ERROR] [BOT TOKEN] Failed to validate VK token")
            return {"valid": False, "error": "Internal server error"}

    async def validate_all_tokens(self) -> Dict[str, Dict[str, Any]]:
        """Validate all bot tokens and return summary."""
        logger.info("=" * 80)
        logger.info("[BOT TOKEN] Validating bot tokens...")
        logger.info("=" * 80)

        results = {
            "twitch": await self.validate_twitch_bot_token(),
            "vk": await self.validate_vk_bot_token(),
        }

        logger.info("=" * 80)
        logger.info("[BOT TOKEN] Validation Summary:")
        logger.info("  Twitch: %s", "[VALID]" if results["twitch"]["valid"] else "[INVALID]")
        logger.info("  VK Live: %s", "[VALID]" if results["vk"]["valid"] else "[INVALID]")
        logger.info("=" * 80)

        return results

    async def start_monitoring(self, check_interval: int = 3600):
        """Start periodic validation task."""
        if self._monitoring_task and not self._monitoring_task.done():
            logger.warning("[BOT TOKEN] Monitoring already running")
            return

        logger.info(f"[BOT TOKEN] Starting token monitoring (interval: {check_interval}s)")
        self._monitoring_task = asyncio.create_task(self._monitoring_loop(check_interval))

    async def stop_monitoring(self):
        """Stop periodic validation task."""
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
            logger.info("[BOT TOKEN] Monitoring stopped")

    async def _monitoring_loop(self, interval: int):
        """Periodic monitor loop."""
        while True:
            try:
                await asyncio.sleep(interval)
                logger.info("[BOT TOKEN] Periodic token validation...")
                results = await self.validate_all_tokens()

                if not results["twitch"]["valid"]:
                    logger.error("[ALERT] Twitch bot token is invalid! Bot will not work.")
                if not results["vk"]["valid"]:
                    logger.warning("[ALERT] VK bot token is invalid.")
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("[ERROR] Error in token monitoring loop")

    def get_status(self) -> Dict[str, Any]:
        """Return latest in-memory validation status."""
        return {
            "twitch": {
                "valid": self.twitch_token_valid,
                "last_check": self.last_twitch_check.isoformat() if self.last_twitch_check else None,
            },
            "vk": {
                "valid": self.vk_token_valid,
                "last_check": self.last_vk_check.isoformat() if self.last_vk_check else None,
            },
            "monitoring_active": self._monitoring_task is not None and not self._monitoring_task.done(),
        }


bot_token_validator = BotTokenValidator()

