#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Provider-aware TTS manager for bot_service.

Priority order:
1. Advanced providers (F5/GCloud) based on current settings.
2. Basic gTTS as always-on fallback.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import aiohttp

from constants import (
    TTS_DEFAULT_VOLUME,
    TTS_HEALTH_CHECK_INTERVAL,
    TTS_MAX_RETRIES,
    TTS_RETRY_DELAY,
)
from core.config import settings
from core.internal_service_auth import TTSAuthConfigError, build_tts_auth_headers
from core.project_paths import TEMP_DIR
from services.tts.basic_tts import get_basic_tts
from services.tts.google_cloud_tts import (
    get_google_cloud_tts,
    is_gemini_or_chirp_voice,
    normalize_gcloud_mood,
)
from services.tts.language_routing import enrich_tts_settings_with_language_routing
from services.tts.provider_audio import (
    build_provider_success_result as build_provider_success_result_impl,
    materialize_provider_audio as materialize_provider_audio_impl,
    persist_audio_bytes as persist_audio_bytes_impl,
    resolve_provider_audio_fetch_headers as resolve_provider_audio_fetch_headers_impl,
)
from services.tts.provider_routing import (
    resolve_advanced_provider_mode,
    resolve_requested_provider,
)
from services.tts.provider_utils import (
    ProviderRoutingError,
    get_provider_service_url,
    get_synthesis_upstream_params,
    get_synthesis_upstream_url,
    normalize_local_tts_endpoint_url,
    normalize_provider,
    should_route_provider_via_gateway,
)

logger = logging.getLogger(__name__)
_GEMINI_SPEAKER_PATTERN = re.compile(r"^[A-Z][A-Za-z0-9_]{1,63}$")


def _gcloud_voice_quality_rank(voice_name: Optional[str]) -> int:
    key = (voice_name or "").lower()
    if _GEMINI_SPEAKER_PATTERN.match(voice_name or ""):
        return 0
    if "gemini" in key:
        return 0
    if "chirp3-hd" in key:
        return 1
    if "neural2" in key:
        return 2
    if "wavenet" in key:
        return 3
    if "studio" in key:
        return 4
    if "journey" in key:
        return 5
    if "standard" in key:
        return 9
    return 6


class TTSManager:
    """Coordinates provider synthesis and fallback to basic TTS."""

    def __init__(self):
        from core import config as config_module

        current_settings = config_module.settings
        self.f5_tts_service_url = current_settings.f5_tts_service_url
        self.backend_url = settings.backend_url

        self.basic_tts = get_basic_tts()
        self.google_cloud_tts = get_google_cloud_tts()

        # Cache health per effective endpoint to avoid cross-endpoint poisoning:
        # a failing local endpoint must not mark the cloud endpoint as unhealthy.
        self._provider_health: Dict[tuple[str, str], bool] = {}
        self._provider_last_health_check: Dict[tuple[str, str], float] = {}
        self._health_check_interval = TTS_HEALTH_CHECK_INTERVAL

        logger.info(
            "[OK] TTS manager initialized: f5_url=%s",
            self.f5_tts_service_url,
        )

    async def get_user_tts_endpoint(
        self,
        user_id: int,
        db_session,
        provider: str = "f5",
    ) -> Optional[Dict[str, Optional[str]]]:
        """Return healthy local endpoint payload for provider if configured."""
        try:
            from repositories.local_tts_repository import LocalTTSRepository

            repo = LocalTTSRepository(db_session)
            normalized_provider = normalize_provider(provider)
            local_config = repo.get_healthy(user_id=user_id, provider=normalized_provider)

            if local_config:
                try:
                    normalized_endpoint = normalize_local_tts_endpoint_url(local_config.endpoint_url)
                except ValueError as error:
                    logger.warning(
                        "[WARN] Ignoring invalid local endpoint for user_id=%s provider=%s: %s",
                        user_id,
                        normalized_provider,
                        error,
                    )
                    return None

                logger.info(
                    "[LOCAL] Using local endpoint for user_id=%s provider=%s endpoint=%s",
                    user_id,
                    normalized_provider,
                    normalized_endpoint,
                )
                return {
                    "endpoint_url": normalized_endpoint,
                    "api_key": str(local_config.api_key or "").strip() or None,
                }

            return None
        except Exception:
            logger.exception("Error getting user local TTS endpoint")
            return None

    def _resolve_provider_audio_fetch_headers(
        self,
        *,
        provider: str,
        endpoint: str,
        resolved_audio_url: str,
        headers: Dict[str, str],
    ) -> Dict[str, str]:
        return resolve_provider_audio_fetch_headers_impl(
            provider=provider,
            endpoint=endpoint,
            resolved_audio_url=resolved_audio_url,
            headers=headers,
            gateway_url=str(getattr(settings, "tts_gateway_url", "") or "").strip().rstrip("/"),
            get_provider_service_url_fn=get_provider_service_url,
            build_tts_auth_headers_fn=build_tts_auth_headers,
        )

    async def check_tts_service_health(
        self,
        force_check: bool = False,
        provider: str = "f5",
        endpoint_override: Optional[str] = None,
        endpoint_api_key: Optional[str] = None,
    ) -> bool:
        """Health check for remote/local provider endpoint with endpoint-aware cache."""
        normalized_provider = normalize_provider(provider)
        use_gateway = False
        if endpoint_override:
            try:
                endpoint = normalize_local_tts_endpoint_url(endpoint_override)
            except ValueError as error:
                if not force_check:
                    logger.warning(
                        "[WARN] Invalid endpoint override for health check provider=%s error=%s",
                        normalized_provider,
                        error,
                    )
                return False
            request_headers = build_tts_auth_headers(
                provider=normalized_provider,
                upstream="local",
                local_api_key=endpoint_api_key,
                strict=False,
            )
            request_params: Dict[str, str] = {}
        else:
            try:
                endpoint = get_synthesis_upstream_url(normalized_provider).rstrip("/")
            except ProviderRoutingError as error:
                if not force_check:
                    logger.warning(
                        "[WARN] %s health check routing error: %s",
                        normalized_provider,
                        error,
                    )
                cache_key = (normalized_provider, "routing_error")
                self._provider_health[cache_key] = False
                self._provider_last_health_check[cache_key] = time.time()
                return False

            use_gateway = should_route_provider_via_gateway(normalized_provider)
            try:
                request_headers = build_tts_auth_headers(
                    provider=normalized_provider,
                    upstream="synthesis",
                    use_gateway=use_gateway,
                    strict=True,
                )
            except TTSAuthConfigError as error:
                if not force_check:
                    logger.warning(
                        "[WARN] %s health check auth configuration error: %s",
                        normalized_provider,
                        error,
                    )
                cache_key = (normalized_provider, endpoint)
                self._provider_health[cache_key] = False
                self._provider_last_health_check[cache_key] = time.time()
                return False

            request_params = (
                get_synthesis_upstream_params(normalized_provider)
                if use_gateway
                else {}
            )
        cache_key = (normalized_provider, endpoint)
        current_time = time.time()
        last_check = self._provider_last_health_check.get(cache_key, 0.0)

        if (not force_check) and (current_time - last_check < self._health_check_interval):
            return self._provider_health.get(cache_key, True)

        try:
            timeout = aiohttp.ClientTimeout(total=5, connect=2)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                health_payload = None
                last_status = None
                health_paths = (
                    ("/health/ready", "/api/health", "/health")
                    if use_gateway
                    else ("/api/health", "/health", "/health/ready")
                )
                for health_path in health_paths:
                    async with session.get(
                        f"{endpoint}{health_path}",
                        headers=request_headers,
                        params=request_params,
                    ) as response:
                        last_status = response.status
                        if response.status != 200:
                            continue
                        try:
                            health_payload = await response.json()
                        except Exception:
                            health_payload = {"status": "healthy"}
                        break

                if health_payload is None:
                    if not force_check:
                        logger.warning(
                            "[WARN] %s health check failed status=%s endpoint=%s",
                            normalized_provider,
                            last_status,
                            endpoint,
                        )
                    self._provider_health[cache_key] = False
                    self._provider_last_health_check[cache_key] = current_time
                    return False

                status_value = str(health_payload.get("status") or "").strip().lower()
                tts_engine_value = str(health_payload.get("tts_engine") or "").strip().lower()
                redis_state = str(health_payload.get("redis") or "").strip().lower()
                scheduler_state = str(health_payload.get("scheduler") or "").strip().lower()
                ready_flag = health_payload.get("ready")

                is_healthy = bool(
                    health_payload.get("tts_engine_loaded", False)
                    or status_value in {"healthy", "ok", "ready"}
                    or tts_engine_value == "ready"
                    or ready_flag is True
                )

                if use_gateway and status_value == "ok":
                    is_healthy = redis_state != "down" and scheduler_state != "stopped"

                previous_state = self._provider_health.get(cache_key)
                if previous_state is not None and previous_state != is_healthy:
                    if is_healthy:
                        logger.info("[OK] %s service is healthy again", normalized_provider)
                    else:
                        logger.warning("[WARN] %s service is unhealthy", normalized_provider)

                self._provider_health[cache_key] = is_healthy
                self._provider_last_health_check[cache_key] = current_time
                return is_healthy

        except asyncio.TimeoutError:
            if not force_check:
                logger.warning("[WARN] %s health check timeout endpoint=%s", normalized_provider, endpoint)
        except aiohttp.ClientError as error:
            if not force_check:
                logger.warning(
                    "[WARN] %s health check connection error endpoint=%s error=%s",
                    normalized_provider,
                    endpoint,
                    error,
                )
        except Exception:
            if not force_check:
                logger.exception("[ERROR] %s health check failed endpoint=%s", normalized_provider, endpoint)

        self._provider_health[cache_key] = False
        self._provider_last_health_check[cache_key] = current_time
        return False

    @staticmethod
    def _enrich_result(
        result: Dict[str, Any],
        *,
        requested_provider: str,
        actual_provider: str,
        fallback_used: bool,
        fallback_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = dict(result or {})
        payload["requested_provider"] = requested_provider
        payload["actual_provider"] = actual_provider
        payload["fallback_used"] = bool(fallback_used)
        if fallback_reason:
            payload["fallback_reason"] = fallback_reason
        elif "fallback_reason" in payload:
            payload.pop("fallback_reason", None)
        return payload

    async def _persist_audio_bytes(
        self,
        *,
        audio_bytes: bytes,
        provider: str,
        source_url: Optional[str],
        content_type: Optional[str],
    ) -> Dict[str, str]:
        return await persist_audio_bytes_impl(
            audio_bytes=audio_bytes,
            provider=provider,
            source_url=source_url,
            content_type=content_type,
            backend_url=self.backend_url,
            temp_dir=TEMP_DIR,
        )

    async def _materialize_provider_audio(
        self,
        *,
        session: aiohttp.ClientSession,
        provider: str,
        audio_url: Optional[str],
        endpoint: str,
        headers: Dict[str, str],
    ) -> Dict[str, Optional[str]]:
        return await materialize_provider_audio_impl(
            session=session,
            provider=provider,
            audio_url=audio_url,
            endpoint=endpoint,
            headers=headers,
            backend_url=self.backend_url,
            resolve_provider_audio_fetch_headers_fn=self._resolve_provider_audio_fetch_headers,
            persist_audio_bytes_fn=self._persist_audio_bytes,
        )

    async def _build_provider_success_result(
        self,
        *,
        session: aiohttp.ClientSession,
        provider: str,
        endpoint: str,
        headers: Dict[str, str],
        tts_type: str,
        result_payload: Dict[str, Any],
        volume_level: float,
    ) -> Dict[str, Any]:
        return await build_provider_success_result_impl(
            session=session,
            provider=provider,
            endpoint=endpoint,
            headers=headers,
            tts_type=tts_type,
            result_payload=result_payload,
            volume_level=volume_level,
            materialize_provider_audio_fn=self._materialize_provider_audio,
        )

    @staticmethod
    def _build_worker_job_payload(
        *,
        channel_name: str,
        text: str,
        author: str,
        user_id: Optional[int],
        volume_level: float,
        tts_settings: Optional[dict[str, Any]],
        word_filter: Optional[list],
        blocked_users: Optional[list],
        provider: str,
        voice: Optional[str],
    ) -> dict[str, Any]:
        request_settings = dict(tts_settings or {})
        if provider:
            request_settings.setdefault("advanced_provider", provider)
        return {
            "channel_name": channel_name,
            "text": text,
            "author": author,
            "user_id": user_id,
            "volume_level": volume_level,
            "tts_settings": request_settings,
            "word_filter": list(word_filter or []),
            "blocked_users": list(blocked_users or []),
            "provider": provider,
            "voice": voice,
            "voice_map": {
                "f5": request_settings.get("voice"),
            },
        }

    async def _synthesize_via_worker_control(
        self,
        *,
        provider: str,
        managed_only: bool,
        channel_name: str,
        text: str,
        author: str,
        user_id: Optional[int],
        volume_level: float,
        tts_settings: Optional[dict[str, Any]],
        word_filter: Optional[list],
        blocked_users: Optional[list],
        db_session,
    ) -> Optional[Dict[str, Any]]:
        if not db_session:
            return None

        from services.worker_control.service import WorkerControlPlaneService

        request_settings = dict(tts_settings or {})
        voice = str(
            request_settings.get("voice")
            or ""
        ).strip() or None

        worker_service = WorkerControlPlaneService(db_session)
        final_job = await worker_service.synthesize_via_worker(
            provider=provider,
            text=text,
            voice=voice,
            payload=self._build_worker_job_payload(
                channel_name=channel_name,
                text=text,
                author=author,
                user_id=user_id,
                volume_level=volume_level,
                tts_settings=request_settings,
                word_filter=word_filter,
                blocked_users=blocked_users,
                provider=provider,
                voice=voice,
            ),
            owner_user_id=user_id,
            created_by_user_id=user_id,
            managed_only=managed_only,
            timeout_seconds=settings.worker_result_timeout_seconds,
        )
        if final_job is None:
            return None

        if final_job.get("status") != "completed":
            error_message = (
                final_job.get("error_message")
                or f"worker job ended with status={final_job.get('status')}"
            )
            return {
                "success": False,
                "error": error_message,
                "worker_path_used": True,
                "worker_mode": final_job.get("worker_mode"),
                "worker_key": final_job.get("worker_key"),
                "job_id": final_job.get("id"),
            }

        result_payload = dict(final_job.get("result_payload") or {})
        selected_voice = (
            result_payload.get("selected_voice")
            or result_payload.get("voice")
            or voice
            or "default_voice"
        )
        return {
            "success": True,
            "voice": selected_voice,
            "selected_voice": selected_voice,
            "volume": volume_level,
            "tts_type": result_payload.get("tts_type") or "ai_f5",
            "audio_url": final_job.get("result_audio_url"),
            "audio_path": result_payload.get("audio_path"),
            "duration": result_payload.get("duration"),
            "provider": provider,
            "worker_mode": final_job.get("worker_mode"),
            "worker_key": final_job.get("worker_key"),
            "job_id": final_job.get("id"),
            "worker_path_used": True,
            "meta": result_payload.get("meta") if isinstance(result_payload.get("meta"), dict) else {},
            "speed_preset": result_payload.get("speed_preset")
            or (
                result_payload.get("meta", {}).get("speed_preset")
                if isinstance(result_payload.get("meta"), dict)
                else None
            ),
            "cfg_strength": result_payload.get("cfg_strength")
            or (
                result_payload.get("meta", {}).get("cfg_strength")
                if isinstance(result_payload.get("meta"), dict)
                else None
            ),
            "endpoint_used": result_payload.get("endpoint_used")
            or (
                result_payload.get("meta", {}).get("endpoint_used")
                if isinstance(result_payload.get("meta"), dict)
                else None
            ),
        }

    async def synthesize_tts(
        self,
        channel_name: str,
        text: str,
        author: str,
        user_id: int = None,
        volume_level: float = TTS_DEFAULT_VOLUME,
        use_ai_tts: bool = False,
        use_basic_tts: bool = True,
        connection_manager=None,
        tts_settings: dict = None,
        word_filter: list = None,
        blocked_users: list = None,
        db_session=None,
        engine: Optional[str] = None,
    ) -> Dict:
        """Synthesize speech with provider-first routing and explicit fallback metadata."""

        settings_dict = enrich_tts_settings_with_language_routing(tts_settings, text)
        resolved_engine = (engine or ("f5tts" if use_ai_tts else "gtts")).strip().lower()
        logger.info("[MIC] Engine resolved: %s", resolved_engine)
        requested_provider = resolve_requested_provider(
            resolved_engine=resolved_engine,
            settings_dict=settings_dict,
        )
        language_routing = settings_dict.get("language_routing") if isinstance(settings_dict.get("language_routing"), dict) else {}
        logger.info(
            "[TRACE] TTS language routing route_target=%s detected_language=%s requires_bilingual=%s reason=%s latin_preview=%s",
            language_routing.get("route_target", "-"),
            language_routing.get("detected_language", "-"),
            bool(language_routing.get("requires_bilingual_checkpoint")),
            language_routing.get("decision_reason", "-"),
            ",".join(language_routing.get("plain_latin_words_preview", [])[:5]) if isinstance(language_routing.get("plain_latin_words_preview"), list) else "-",
        )
        fallback_reason: Optional[str] = None

        # Priority A: Google Cloud TTS
        if resolved_engine == "gcloud":
            try:
                result = await self._synthesize_via_google_cloud_tts(
                    text=text,
                    volume_level=volume_level,
                    tts_settings=settings_dict,
                )
                if result.get("success"):
                    logger.info("[OK] Google Cloud TTS synthesis succeeded")
                    self.cleanup_old_files_if_needed()
                    return self._enrich_result(
                        result,
                        requested_provider="gcloud",
                        actual_provider="gcloud",
                        fallback_used=False,
                    )
                fallback_reason = f"gcloud_error:{result.get('error') or 'unknown'}"
                logger.warning("[WARN] Google Cloud TTS failed: %s", result.get("error"))
            except Exception:
                fallback_reason = "gcloud_exception"
                logger.exception("[ERROR] Google Cloud TTS execution failed")

        # Priority B: Advanced provider (F5) with retries
        elif resolved_engine == "f5tts" and use_ai_tts:
            provider = requested_provider
            resolved_mode, _has_explicit_provider_mode = resolve_advanced_provider_mode(
                provider=provider,
                settings_dict=settings_dict,
            )

            if (
                resolved_mode == "local"
                and user_id
                and db_session
                and settings.worker_control_self_host_enabled
            ):
                try:
                    worker_result = await self._synthesize_via_worker_control(
                        provider=provider,
                        managed_only=False,
                        channel_name=channel_name,
                        text=text,
                        author=author,
                        user_id=user_id,
                        volume_level=volume_level,
                        tts_settings=settings_dict,
                        word_filter=word_filter,
                        blocked_users=blocked_users,
                        db_session=db_session,
                    )
                    if worker_result:
                        if worker_result.get("success"):
                            logger.info(
                                "[OK] Self-host worker synthesis succeeded provider=%s worker_key=%s",
                                provider,
                                worker_result.get("worker_key"),
                            )
                            self.cleanup_old_files_if_needed()
                            return self._enrich_result(
                                worker_result,
                                requested_provider=provider,
                                actual_provider=provider,
                                fallback_used=False,
                            )
                        fallback_reason = f"{provider}_worker_failed:{worker_result.get('error') or 'unknown'}"
                        logger.warning(
                            "[WARN] Self-host worker synthesis failed provider=%s worker_key=%s error=%s; "
                            "falling back to legacy endpoint/basic path",
                            provider,
                            worker_result.get("worker_key"),
                            worker_result.get("error"),
                        )
                except Exception:
                    fallback_reason = f"{provider}_worker_control_exception"
                    logger.exception(
                        "[WARN] Self-host worker control path raised unexpectedly provider=%s; "
                        "falling back to legacy endpoint/basic path",
                        provider,
                    )

            if (
                resolved_mode != "local"
                and db_session
                and settings.worker_control_managed_enabled
            ):
                try:
                    worker_result = await self._synthesize_via_worker_control(
                        provider=provider,
                        managed_only=True,
                        channel_name=channel_name,
                        text=text,
                        author=author,
                        user_id=user_id,
                        volume_level=volume_level,
                        tts_settings=settings_dict,
                        word_filter=word_filter,
                        blocked_users=blocked_users,
                        db_session=db_session,
                    )
                    if worker_result:
                        if worker_result.get("success"):
                            logger.info(
                                "[OK] Managed worker synthesis succeeded provider=%s worker_key=%s",
                                provider,
                                worker_result.get("worker_key"),
                            )
                            self.cleanup_old_files_if_needed()
                            return self._enrich_result(
                                worker_result,
                                requested_provider=provider,
                                actual_provider=provider,
                                fallback_used=False,
                            )
                        fallback_reason = f"{provider}_managed_worker_failed:{worker_result.get('error') or 'unknown'}"
                        logger.warning(
                            "[WARN] Managed worker synthesis failed provider=%s worker_key=%s error=%s; "
                            "falling back to gateway/direct/basic path",
                            provider,
                            worker_result.get("worker_key"),
                            worker_result.get("error"),
                        )
                except Exception:
                    fallback_reason = f"{provider}_managed_worker_control_exception"
                    logger.exception(
                        "[WARN] Managed worker control path raised unexpectedly provider=%s; "
                        "falling back to gateway/direct/basic path",
                        provider,
                    )

            endpoint = get_provider_service_url(provider)
            endpoint_api_key: Optional[str] = None
            has_explicit_local_endpoint = False

            if resolved_mode == "local":
                if user_id and db_session:
                    local_endpoint_payload = await self.get_user_tts_endpoint(
                        user_id=user_id,
                        db_session=db_session,
                        provider=provider,
                    )
                    if local_endpoint_payload:
                        endpoint = str(local_endpoint_payload.get("endpoint_url") or endpoint)
                        endpoint_api_key = local_endpoint_payload.get("api_key")
                        has_explicit_local_endpoint = True
                if not has_explicit_local_endpoint:
                    logger.warning(
                        "[WARN] No local endpoint configured for provider=%s user_id=%s; fallback to basic TTS",
                        provider,
                        user_id,
                    )
                    fallback_reason = f"{provider}_local_endpoint_not_configured"

            if resolved_mode != "local" or has_explicit_local_endpoint:
                max_retries = TTS_MAX_RETRIES
                base_retry_delay = TTS_RETRY_DELAY

                is_healthy = await self.check_tts_service_health(
                    provider=provider,
                    endpoint_override=endpoint if has_explicit_local_endpoint else None,
                    endpoint_api_key=endpoint_api_key,
                )
                if not is_healthy:
                    logger.warning(
                        "[WARN] Provider unhealthy provider=%s endpoint=%s; fallback to basic TTS",
                        provider,
                        endpoint,
                    )
                    fallback_reason = f"{provider}_unhealthy"
                else:
                    last_advanced_error: Optional[str] = None
                    for attempt in range(1, max_retries + 1):
                        try:
                            result = await self._synthesize_via_tts_service(
                                channel_name=channel_name,
                                text=text,
                                author=author,
                                user_id=user_id,
                                volume_level=volume_level,
                                connection_manager=connection_manager,
                                tts_settings=settings_dict,
                                word_filter=word_filter,
                                blocked_users=blocked_users,
                                provider=provider,
                                tts_endpoint=endpoint if has_explicit_local_endpoint else None,
                                tts_endpoint_api_key=endpoint_api_key,
                            )
                            if result.get("success"):
                                logger.info(
                                    "[OK] Advanced synthesis succeeded provider=%s attempt=%s/%s",
                                    provider,
                                    attempt,
                                    max_retries,
                                )
                                self.cleanup_old_files_if_needed()
                                return self._enrich_result(
                                    result,
                                    requested_provider=provider,
                                    actual_provider=provider,
                                    fallback_used=False,
                                )

                            last_advanced_error = str(result.get("error") or "provider_failed")
                            logger.warning(
                                "[WARN] Advanced synthesis failed provider=%s attempt=%s/%s error=%s",
                                provider,
                                attempt,
                                max_retries,
                                result.get("error"),
                            )
                        except asyncio.TimeoutError:
                            last_advanced_error = "timeout"
                            logger.warning(
                                "[WARN] Advanced synthesis timeout provider=%s attempt=%s/%s",
                                provider,
                                attempt,
                                max_retries,
                            )
                        except aiohttp.ClientError as error:
                            last_advanced_error = f"connection:{error}"
                            logger.warning(
                                "[WARN] Advanced synthesis connection error provider=%s attempt=%s/%s error=%s",
                                provider,
                                attempt,
                                max_retries,
                                error,
                            )
                        except Exception:
                            last_advanced_error = "exception"
                            logger.exception(
                                "[ERROR] Advanced synthesis exception provider=%s attempt=%s/%s",
                                provider,
                                attempt,
                                max_retries,
                            )

                        if attempt < max_retries:
                            delay = base_retry_delay * (2 ** (attempt - 1))
                            await asyncio.sleep(delay)

                    logger.warning(
                        "[WARN] Advanced provider exhausted retries provider=%s; fallback to basic TTS",
                        provider,
                    )
                    fallback_reason = f"{provider}_failed:{last_advanced_error or 'unknown'}"
        elif resolved_engine == "f5tts":
            fallback_reason = f"{requested_provider}_disabled"

        # Priority C: Basic TTS or explicit fallback.
        if resolved_engine != "gtts" and not use_basic_tts:
            return self._enrich_result(
                {"success": False, "error": fallback_reason or "Advanced provider failed with fallback disabled"},
                requested_provider=requested_provider,
                actual_provider=requested_provider,
                fallback_used=False,
                fallback_reason=fallback_reason,
            )

        try:
            result = await self._synthesize_via_basic_tts(text, volume_level)
            if result.get("success"):
                logger.info("[OK] Basic TTS synthesis succeeded")
                self.cleanup_old_files_if_needed()
                return self._enrich_result(
                    result,
                    requested_provider=requested_provider,
                    actual_provider="gtts",
                    fallback_used=requested_provider != "gtts",
                    fallback_reason=fallback_reason,
                )
            logger.error("[ERROR] Basic TTS synthesis failed: %s", result.get("error"))
            return self._enrich_result(
                {"success": False, "error": "Basic TTS synthesis failed"},
                requested_provider=requested_provider,
                actual_provider="gtts",
                fallback_used=requested_provider != "gtts",
                fallback_reason=fallback_reason,
            )
        except Exception as error:
            logger.exception("[ERROR] Basic TTS execution failed")
            return self._enrich_result(
                {"success": False, "error": f"Basic TTS error: {error}"},
                requested_provider=requested_provider,
                actual_provider="gtts",
                fallback_used=requested_provider != "gtts",
                fallback_reason=fallback_reason,
            )

    async def _synthesize_via_tts_service(
        self,
        channel_name: str,
        text: str,
        author: str,
        user_id: int = None,
        volume_level: float = TTS_DEFAULT_VOLUME,
        connection_manager=None,
        tts_settings: dict = None,
        word_filter: list = None,
        blocked_users: list = None,
        provider: str = "f5",
        tts_endpoint: str = None,
        tts_endpoint_api_key: Optional[str] = None,
    ) -> Dict:
        """Synthesize through remote provider service endpoint."""
        normalized_provider = normalize_provider(provider)
        tts_type = "ai_f5"

        try:
            query_params: Dict[str, Any]
            if tts_endpoint:
                try:
                    endpoint = normalize_local_tts_endpoint_url(tts_endpoint)
                except ValueError as error:
                    logger.warning(
                        "[WARN] Invalid local endpoint during synthesis provider=%s error=%s",
                        normalized_provider,
                        error,
                    )
                    return {"success": False, "error": "Invalid local endpoint configuration"}
                headers = build_tts_auth_headers(
                    provider=normalized_provider,
                    upstream="local",
                    local_api_key=tts_endpoint_api_key,
                    strict=False,
                )
                query_params = {}
            else:
                try:
                    endpoint = get_synthesis_upstream_url(normalized_provider).rstrip("/")
                except ProviderRoutingError as error:
                    return {
                        "success": False,
                        "error": f"Provider routing error: {error}",
                    }

                use_gateway = should_route_provider_via_gateway(normalized_provider)
                headers = build_tts_auth_headers(
                    provider=normalized_provider,
                    upstream="synthesis",
                    use_gateway=use_gateway,
                    strict=True,
                )
                query_params = get_synthesis_upstream_params(normalized_provider)

            request_timeout_total = 30
            timeout = aiohttp.ClientTimeout(
                total=request_timeout_total,
                connect=10,
                sock_read=request_timeout_total,
            )

            request_settings = dict(tts_settings or {})
            request_settings.setdefault("advanced_provider", normalized_provider)
            trace_id = str(request_settings.get("trace_id") or "").strip()
            source_message_id = str(request_settings.get("source_message_id") or "").strip()
            f5_voice = str(request_settings.get("voice") or "").strip()
            voice_map = {}
            if f5_voice:
                voice_map["f5"] = f5_voice
            selected_request_voice = voice_map.get("f5") or f5_voice or "default_voice"

            async with aiohttp.ClientSession(timeout=timeout) as session:
                url = f"{endpoint}/api/tts/synthesize-channel"
                payload = {
                    "channel_name": channel_name,
                    "text": text,
                    "author": author,
                    "user_id": user_id,
                    "volume_level": volume_level,
                    "tts_settings": request_settings,
                    "word_filter": word_filter or [],
                    "blocked_users": blocked_users or [],
                    "provider": normalized_provider,
                    "voice": selected_request_voice,
                    "voice_map": voice_map,
                    "request_id": source_message_id or trace_id or uuid.uuid4().hex,
                    "event_id": source_message_id or None,
                }
                logger.info(
                    "[TRACE] Provider request provider=%s trace_id=%s source_message_id=%s voice=%s endpoint=%s",
                    normalized_provider,
                    trace_id or "-",
                    source_message_id or "-",
                    selected_request_voice,
                    endpoint,
                )

                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                    params=query_params,
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(
                            "[ERROR] Provider returned error provider=%s trace_id=%s source_message_id=%s status=%s body=%s",
                            normalized_provider,
                            trace_id or "-",
                            source_message_id or "-",
                            response.status,
                            error_text,
                        )
                        return {
                            "success": False,
                            "error": f"Provider error: {response.status}",
                        }

                    result = await response.json()
                    if isinstance(result, dict) and result.get("success") is False:
                        upstream_error = str(
                            result.get("error")
                            or result.get("detail")
                            or "Provider returned unsuccessful payload"
                        ).strip()
                        logger.error(
                            "[ERROR] Provider returned unsuccessful payload provider=%s trace_id=%s source_message_id=%s error=%s body=%s",
                            normalized_provider,
                            trace_id or "-",
                            source_message_id or "-",
                            upstream_error,
                            result,
                        )
                        return {
                            "success": False,
                            "error": upstream_error or "Provider returned unsuccessful payload",
                        }

                    provider_result = await self._build_provider_success_result(
                        session=session,
                        provider=normalized_provider,
                        endpoint=endpoint,
                        headers=headers,
                        tts_type=tts_type,
                        result_payload=result,
                        volume_level=volume_level,
                    )
                    selected_voice = provider_result.get("voice")

                    # Volume is applied during playback. Avoid re-synthesizing the same
                    # phrase a second time just to change gain metadata.
                    if connection_manager and selected_voice:
                        priority_volume = connection_manager.get_voice_volume(channel_name, selected_voice)
                        if priority_volume != TTS_DEFAULT_VOLUME:
                            provider_result["volume"] = priority_volume

                    return provider_result

        except asyncio.TimeoutError:
            logger.warning("[WARN] Provider request timeout provider=%s", normalized_provider)
            return {"success": False, "error": "Request timeout"}
        except TTSAuthConfigError as error:
            logger.warning(
                "[WARN] Provider request auth configuration error provider=%s error=%s",
                normalized_provider,
                error,
            )
            return {"success": False, "error": str(error)}
        except aiohttp.ClientError as error:
            logger.warning("[WARN] Provider request connection error provider=%s error=%s", normalized_provider, error)
            return {"success": False, "error": f"Connection error: {error}"}
        except Exception:
            logger.exception("[ERROR] Provider request failed provider=%s", normalized_provider)
            return {"success": False, "error": "Internal server error"}

    async def _synthesize_via_basic_tts(self, text: str, volume_level: float) -> Dict:
        """Synthesize through local basic gTTS implementation."""
        try:
            audio_path = self.basic_tts.synthesize_speech(
                text=text,
                volume_level=volume_level,
                speed=1.0,
            )

            if not audio_path:
                logger.error("[ERROR] Basic TTS synthesize_speech returned no path")
                return {"success": False, "error": "Basic TTS synthesis failed"}

            filename = Path(audio_path).name
            audio_url = f"{self.backend_url}/api/tts/audio/{filename}"

            return {
                "success": True,
                "voice": "basic_gtts",
                "volume": volume_level,
                "tts_type": "basic_gtts",
                "audio_url": audio_url,
                "audio_path": audio_path,
            }

        except Exception:
            logger.exception("[ERROR] Basic TTS synthesis exception")
            return {"success": False, "error": "Internal server error"}

    async def _synthesize_via_google_cloud_tts(
        self,
        text: str,
        volume_level: float,
        tts_settings: dict,
    ) -> Dict:
        """Synthesize via Google Cloud TTS provider."""
        try:
            voice_pool = []
            if tts_settings:
                voice_pool = tts_settings.get("gcloud_voices") or tts_settings.get("gcloudVoices") or []

            cleaned_voice_pool = [
                str(voice).strip()
                for voice in voice_pool
                if isinstance(voice, str) and str(voice).strip()
            ]
            filtered_voice_pool = [
                voice
                for voice in cleaned_voice_pool
                if is_gemini_or_chirp_voice(voice)
            ]

            if cleaned_voice_pool and not filtered_voice_pool:
                logger.warning(
                    "[WARN] All saved Google voices are legacy/non-premium. Gemini/Chirp only is supported."
                )

            gemini_voice_pool = [
                voice
                for voice in filtered_voice_pool
                if _gcloud_voice_quality_rank(voice) == 0
            ]
            random_pool = gemini_voice_pool or filtered_voice_pool

            fallback_voice = tts_settings.get("voice") if tts_settings else None
            if fallback_voice and not is_gemini_or_chirp_voice(fallback_voice):
                fallback_voice = None

            voice_name = random.choice(random_pool) if random_pool else fallback_voice
            gcloud_mood = normalize_gcloud_mood(
                (tts_settings or {}).get("gcloud_mood")
                or (tts_settings or {}).get("gcloudMood")
            )

            result = await self.google_cloud_tts.synthesize_speech(
                text=text,
                volume_level=volume_level,
                speed=1.0,
                voice_name=voice_name,
                mood=gcloud_mood,
            )

            if not result.get("success"):
                return result

            if result.get("fallback_used"):
                logger.warning(
                    "[WARN] Google Cloud runtime fallback requested_model=%s resolved_voice=%s",
                    result.get("requested_model") or "-",
                    result.get("voice") or "-",
                )

            audio_path = result.get("audio_path")
            if not audio_path:
                return {"success": False, "error": "No audio_path returned"}

            filename = Path(audio_path).name
            audio_url = f"{self.backend_url}/api/tts/audio/{filename}"

            return {
                "success": True,
                "voice": result.get("voice") or "google_cloud",
                "volume": volume_level,
                "tts_type": "google_cloud",
                "audio_url": audio_url,
                "audio_path": audio_path,
                "auth_mode": result.get("auth_mode"),
                "requested_model": result.get("requested_model"),
                "fallback_used": bool(result.get("fallback_used")),
            }

        except Exception:
            logger.exception("[ERROR] Google Cloud TTS synthesis exception")
            return {"success": False, "error": "Internal server error"}

    async def _upload_to_tts_service(self, audio_path: str) -> Optional[str]:
        """Upload an audio file to the F5 service for temporary serving."""
        try:
            import aiofiles

            filename = Path(audio_path).name
            target_url = get_provider_service_url("f5").rstrip("/")

            async with aiofiles.open(audio_path, "rb") as file_handle:
                audio_data = await file_handle.read()

            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                data = aiohttp.FormData()
                data.add_field("file", audio_data, filename=filename, content_type="audio/wav")

                headers = build_tts_auth_headers(
                    provider="f5",
                    upstream="voice",
                    strict=True,
                )
                async with session.post(
                    f"{target_url}/api/upload-audio",
                    data=data,
                    headers=headers,
                ) as response:
                    if response.status != 200:
                        logger.warning("[WARN] Could not upload audio to F5 service status=%s", response.status)
                        return None

                    await response.json()
                    return f"{target_url}/api/audio/{filename}"

        except TTSAuthConfigError as error:
            logger.warning("[WARN] Upload to provider skipped due to auth configuration error: %s", error)
            return None
        except Exception:
            logger.exception("[ERROR] Upload to provider service failed")
            return None

    def cleanup_old_files(self):
        """Clean old temporary files from basic TTS runtime."""
        try:
            self.basic_tts.cleanup_old_files()
        except Exception:
            logger.exception("[ERROR] Basic TTS cleanup failed")

    def cleanup_old_files_if_needed(self):
        """Periodic cleanup every 10 synthesis operations."""
        if not hasattr(self, "_synthesis_count"):
            self._synthesis_count = 0

        self._synthesis_count += 1
        if self._synthesis_count % 10 == 0:
            self.cleanup_old_files()


_tts_manager_instance = None


def get_tts_manager() -> TTSManager:
    """Return singleton TTS manager instance."""
    global _tts_manager_instance
    if _tts_manager_instance is None:
        _tts_manager_instance = TTSManager()
    return _tts_manager_instance
