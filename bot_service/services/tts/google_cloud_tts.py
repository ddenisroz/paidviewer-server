#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google Cloud Text-to-Speech integration.
Provides higher-quality TTS with a fallback path handled by TTSManager.
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List

import httpx
from pydub import AudioSegment

from core.config import settings
from core.project_paths import TEMP_DIR
from services.tts.basic_tts import get_basic_tts

try:
    import google.auth
    from google.auth.transport.requests import Request as GoogleAuthRequest
except Exception:  # pragma: no cover - optional runtime dependency handling
    google = None  # type: ignore[assignment]
    GoogleAuthRequest = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_DEFAULT_VOICES = {
    "ru": ("ru-RU", "ru-RU-Standard-D"),
    "en": ("en-US", "en-US-Standard-C"),
}

_VOICES_CACHE: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
_VOICES_CACHE_TTL = 6 * 60 * 60
_GEMINI_MODEL_NAME = "gemini-2.5-flash-tts"
_GCLOUD_DEFAULT_MOOD = "neutral"
_GCLOUD_MOOD_PROMPTS = {
    "neutral": "Speak naturally, clearly, and conversationally.",
    "sad": "Speak softly with a calm, subdued tone.",
    "happy": "Speak warmly with a cheerful, upbeat tone.",
}
_GEMINI_ALIAS_PATTERN = re.compile(r"^([a-z]{2}-[A-Z]{2})-Gemini-([A-Za-z0-9_]+)$")
_CHIRP_HD_PATTERN = re.compile(r"^([a-z]{2}-[A-Z]{2})-Chirp3-HD-([A-Za-z0-9_]+)$")
_GEMINI_SPEAKER_PATTERN = re.compile(r"^[A-Z][A-Za-z0-9_]{1,63}$")
_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


def _parse_voice_name(voice_name: str) -> Optional[Tuple[str, str]]:
    """Parse voice name like ru-RU-Standard-D into (language_code, voice_name)."""
    if not voice_name:
        return None
    match = re.match(r"^([a-z]{2}-[A-Z]{2})-.+", voice_name)
    if not match:
        return None
    return match.group(1), voice_name


def _google_error_payload(status_code: Optional[int], raw_text: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = data or {}
    error_node = data.get("error", {}) if isinstance(data, dict) else {}
    api_message = error_node.get("message") or raw_text or "Google TTS request failed"
    hint = None
    code = status_code

    if code == 403:
        hint = (
            "Enable Cloud Text-to-Speech API for your Google project, verify billing, "
            "and ensure IAM access for the caller (ADC/service account or API key restrictions)."
        )
        if "unregistered callers" in api_message.lower():
            hint = (
                "Unauthenticated API key caller was rejected. Use ADC/Bearer auth for Gemini voices "
                "or check API key restrictions and enabled APIs."
            )
    elif code == 401:
        hint = "Invalid Google auth token/key. Re-run ADC login or verify GOOGLE_CLOUD_API_KEY."
    elif code == 400:
        hint = "Bad Google TTS request payload or unsupported voice/language."

    return {
        "success": False,
        "error": api_message,
        "hint": hint,
        "status_code": code,
    }


def _google_auth_not_configured_payload() -> Dict[str, Any]:
    return {
        "success": False,
        "error": "Google TTS authentication is not configured",
        "hint": (
            "Configure ADC via `gcloud auth application-default login` + "
            "`gcloud auth application-default set-quota-project <PROJECT_ID>`, "
            "or set GOOGLE_CLOUD_API_KEY."
        ),
        "status_code": None,
    }


def _voice_quality_rank(voice_name: Optional[str]) -> int:
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


def is_gemini_or_chirp_voice(
    voice_name: Optional[str],
    model_name: Optional[str] = None,
) -> bool:
    """
    Return True only for Gemini or Chirp3-HD voice families.

    Supports:
    - synthetic aliases: xx-XX-Gemini-<Speaker>
    - Chirp3-HD canonical names
    - native Gemini speaker ids (e.g. Aoede/Kore) with modelName
    """
    raw_voice = (voice_name or "").strip()
    raw_model = (model_name or "").strip()
    key_voice = raw_voice.lower()
    key_model = raw_model.lower()

    if "gemini" in key_voice or "gemini" in key_model:
        return True
    if "chirp3-hd" in key_voice or "chirp3-hd" in key_model:
        return True
    if _CHIRP_HD_PATTERN.match(raw_voice):
        return True
    if _GEMINI_ALIAS_PATTERN.match(raw_voice):
        return True
    if _GEMINI_SPEAKER_PATTERN.match(raw_voice):
        return True
    return False


def _filter_gemini_and_chirp_voices(voices: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep only Gemini and Chirp3-HD families in the returned voice list."""
    return [
        voice
        for voice in voices
        if is_gemini_or_chirp_voice(
            voice_name=str(voice.get("name") or ""),
            model_name=str(voice.get("modelName") or ""),
        )
    ]


def _normalize_model_name(model_name: Optional[str]) -> Optional[str]:
    raw = (model_name or "").strip()
    if not raw:
        return None
    key = raw.lower()
    if key in {"gemini-2.5-pro-tts", "gemini-2.5-flash-tts"}:
        return key
    if key.startswith("gemini-"):
        return key
    return raw


def normalize_gcloud_mood(mood: Optional[str]) -> str:
    key = str(mood or "").strip().lower()
    if key in _GCLOUD_MOOD_PROMPTS:
        return key
    return _GCLOUD_DEFAULT_MOOD


def get_gcloud_prompt_for_mood(mood: Optional[str]) -> str:
    return _GCLOUD_MOOD_PROMPTS[normalize_gcloud_mood(mood)]


def _sorted_voices(voices: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        voices,
        key=lambda voice: (
            _voice_quality_rank(voice.get("name")),
            (voice.get("name") or "").lower(),
        ),
    )


def _add_gemini_aliases(voices: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Add synthetic Gemini aliases from Chirp3-HD voices so users can explicitly
    pick Gemini profile in UI while keeping fallback compatibility.
    """
    existing_names = {str(v.get("name") or "").strip() for v in voices}
    native_gemini_speakers = {
        str(v.get("name") or "").strip()
        for v in voices
        if "gemini" in str(v.get("modelName") or "").lower()
    }
    aliases: List[Dict[str, Any]] = []

    for voice in voices:
        original_name = str(voice.get("name") or "").strip()
        match = _CHIRP_HD_PATTERN.match(original_name)
        if not match:
            continue

        language_code, speaker_name = match.groups()
        alias_name = f"{language_code}-Gemini-{speaker_name}"
        if alias_name in existing_names or speaker_name in native_gemini_speakers:
            continue

        alias_voice = dict(voice)
        alias_voice["name"] = alias_name
        alias_voice["modelName"] = _GEMINI_MODEL_NAME
        alias_voice["fallbackVoiceName"] = original_name
        alias_voice["isGeminiAlias"] = True
        aliases.append(alias_voice)
        existing_names.add(alias_name)

    return voices + aliases


def _resolve_voice_request(
    detected_lang: str,
    requested_voice_name: Optional[str],
    requested_model_name: Optional[str] = None,
) -> Tuple[str, str, Optional[str], Optional[str]]:
    """
    Resolve (language_code, voice_name, model_name, fallback_voice_name).
    """
    language_code, default_voice = _DEFAULT_VOICES.get(detected_lang, _DEFAULT_VOICES["ru"])
    normalized_model_name = _normalize_model_name(requested_model_name)
    raw_voice = (requested_voice_name or "").strip()
    if not raw_voice:
        return language_code, default_voice, normalized_model_name, None

    gemini_alias_match = _GEMINI_ALIAS_PATTERN.match(raw_voice)
    if gemini_alias_match:
        alias_language, speaker_name = gemini_alias_match.groups()
        fallback_voice_name = f"{alias_language}-Chirp3-HD-{speaker_name}"
        return alias_language, speaker_name, normalized_model_name or _GEMINI_MODEL_NAME, fallback_voice_name

    # Native Gemini names are plain speaker ids like "Kore", "Aoede", etc.
    # If such value is selected, keep it as-is and pin Gemini model explicitly.
    if _GEMINI_SPEAKER_PATTERN.match(raw_voice):
        fallback_voice_name = f"{language_code}-Chirp3-HD-{raw_voice}"
        return language_code, raw_voice, normalized_model_name or _GEMINI_MODEL_NAME, fallback_voice_name

    parsed_voice = _parse_voice_name(raw_voice)
    if parsed_voice:
        return parsed_voice[0], parsed_voice[1], normalized_model_name, None

    return language_code, default_voice, normalized_model_name, None


class GoogleCloudTTS:
    """Google Cloud TTS client."""

    def __init__(self, temp_dir: Optional[Path] = None):
        self.temp_dir = temp_dir or (TEMP_DIR / "tts_audio")
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.basic_tts = get_basic_tts()
        self._adc_credentials: Optional[Any] = None
        self._adc_available = False
        self._google_cloud_project_id = self._resolve_project_id()
        self._init_adc_credentials()
        if not self._adc_available and not self._get_api_key():
            log_fn = logger.info if settings.is_development else logger.warning
            log_fn(
                "[GCLOUD] Google Cloud TTS auth is not configured. "
                "Set ADC (`gcloud auth application-default login`) or GOOGLE_CLOUD_API_KEY."
            )
        logger.info("[OK] Google Cloud TTS initialized. Temp dir: %s", self.temp_dir)

    def _resolve_project_id(self, detected_project_id: Optional[str] = None) -> Optional[str]:
        candidates = [
            settings.google_cloud_project_id,
            os.getenv("GOOGLE_CLOUD_PROJECT_ID"),
            os.getenv("GOOGLE_CLOUD_PROJECT"),
            os.getenv("GCLOUD_PROJECT"),
            os.getenv("GOOGLE_CLOUD_QUOTA_PROJECT"),
            detected_project_id,
        ]
        for raw in candidates:
            if not raw:
                continue
            project_id = str(raw).strip().strip('"').strip("'")
            if project_id:
                return project_id
        return None

    def _init_adc_credentials(self) -> None:
        if google is None:
            logger.info("[INFO] google-auth is unavailable; skipping ADC for Google TTS")
            return

        try:
            credentials, detected_project_id = google.auth.default(scopes=[_CLOUD_PLATFORM_SCOPE])
            self._adc_credentials = credentials
            self._adc_available = True
            self._google_cloud_project_id = self._resolve_project_id(detected_project_id)
            quota_project_id = getattr(credentials, "quota_project_id", None)
            logger.info(
                "[OK] Google ADC initialized for TTS (project=%s, quota_project=%s)",
                self._google_cloud_project_id or "-",
                quota_project_id or "-",
            )
        except Exception as exc:
            self._adc_credentials = None
            self._adc_available = False
            logger.info("[INFO] Google ADC unavailable for TTS, fallback to API key: %s", exc)

    async def _build_auth_variants(self) -> List[Dict[str, Any]]:
        variants: List[Dict[str, Any]] = []

        adc_headers = await self._get_adc_headers()
        if adc_headers:
            variants.append({
                "mode": "adc",
                "headers": adc_headers,
                "params": {},
            })

        api_key = self._get_api_key()
        if api_key:
            variants.append({
                "mode": "api_key",
                "headers": {"x-goog-api-key": api_key},
                "params": {"key": api_key},
            })

        return variants

    async def _get_adc_headers(self) -> Optional[Dict[str, str]]:
        if not self._adc_available or self._adc_credentials is None or GoogleAuthRequest is None:
            return None

        def _refresh_token() -> Optional[str]:
            credentials = self._adc_credentials
            if credentials is None:
                return None

            is_valid = bool(getattr(credentials, "valid", False))
            is_expired = bool(getattr(credentials, "expired", False))
            token = getattr(credentials, "token", None)
            if not is_valid or is_expired or not token:
                credentials.refresh(GoogleAuthRequest())
            return getattr(credentials, "token", None)

        try:
            token = await asyncio.to_thread(_refresh_token)
        except Exception:
            logger.exception("[WARN] Failed to refresh Google ADC token")
            return None

        if not token:
            return None

        quota_project_id = (
            getattr(self._adc_credentials, "quota_project_id", None)
            or self._google_cloud_project_id
        )
        headers = {"Authorization": f"Bearer {token}"}
        if quota_project_id:
            headers["x-goog-user-project"] = str(quota_project_id)
        return headers

    async def _request_with_auth_fallback(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        payload: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[httpx.Response], Optional[str]]:
        auth_variants = await self._build_auth_variants()
        if not auth_variants:
            return None, None

        last_response: Optional[httpx.Response] = None
        last_mode: Optional[str] = None

        for index, variant in enumerate(auth_variants):
            request_headers = dict(variant.get("headers") or {})
            request_params = dict(variant.get("params") or {})
            if params:
                request_params.update(params)

            if method.upper() == "POST":
                response = await client.post(
                    url,
                    json=payload,
                    params=request_params,
                    headers=request_headers,
                )
            else:
                response = await client.get(
                    url,
                    params=request_params,
                    headers=request_headers,
                )

            mode = str(variant.get("mode") or "unknown")
            if response.status_code == 200:
                return response, mode

            last_response = response
            last_mode = mode
            has_next_variant = index + 1 < len(auth_variants)
            if has_next_variant and response.status_code in {401, 403}:
                logger.warning(
                    "[WARN] Google TTS auth via %s failed with %s, trying fallback auth",
                    mode,
                    response.status_code,
                )
                continue
            break

        return last_response, last_mode

    @staticmethod
    def _get_api_key() -> Optional[str]:
        """
        Return API key intended for Google Cloud TTS.
        Tries explicit TTS keys first, then common aliases as fallback.
        """
        candidates = [
            settings.google_tts_api_key,
            settings.google_cloud_api_key,
            os.getenv("GOOGLE_TTS_API_KEY"),
            os.getenv("GOOGLE_CLOUD_API_KEY"),
            os.getenv("GOOGLE_API_KEY"),
            settings.youtube_api_key,  # legacy/shared key fallback
        ]

        for raw in candidates:
            if not raw:
                continue
            key = str(raw).strip().strip('"').strip("'")
            if key:
                return key
        return None

    async def synthesize_speech(
        self,
        text: str,
        volume_level: float = 50.0,
        speed: float = 1.0,
        voice_name: Optional[str] = None,
        prompt: Optional[str] = None,
        mood: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Synthesize speech via Google Cloud TTS and return audio path/metadata."""
        processed_text = self.basic_tts.preprocess_text(text)
        if not processed_text:
            return {"success": False, "error": "Empty or filtered text"}

        detected_lang = self.basic_tts.detect_language(processed_text)
        language_code, resolved_voice_name, model_name, fallback_voice_name = _resolve_voice_request(
            detected_lang=detected_lang,
            requested_voice_name=voice_name,
            requested_model_name=model_name,
        )

        voice_payload: Dict[str, Any] = {
            "languageCode": language_code,
            "name": resolved_voice_name,
        }
        if model_name:
            voice_payload["modelName"] = model_name

        resolved_mood = normalize_gcloud_mood(mood)
        explicit_prompt = (prompt or "").strip()
        normalized_prompt = explicit_prompt or get_gcloud_prompt_for_mood(resolved_mood)
        input_payload: Dict[str, Any] = {"text": processed_text}
        if normalized_prompt and model_name:
            input_payload["prompt"] = normalized_prompt

        requested_model_name = model_name
        fallback_used = False

        logger.info(
            "[GCLOUD] TTS request resolved: input_voice=%s resolved_voice=%s model=%s lang=%s mood=%s prompt=%s",
            voice_name or "-",
            resolved_voice_name,
            model_name or "-",
            language_code,
            resolved_mood,
            "yes" if normalized_prompt else "no",
        )

        payload = {
            "input": input_payload,
            "voice": voice_payload,
            "audioConfig": {
                "audioEncoding": "LINEAR16",
                "sampleRateHertz": 24000,
                "speakingRate": max(0.25, min(4.0, float(speed)))
            }
        }

        url = "https://texttospeech.googleapis.com/v1/text:synthesize"

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response, auth_mode = await self._request_with_auth_fallback(
                    client,
                    "POST",
                    url,
                    payload=payload,
                )
                if response is None:
                    return _google_auth_not_configured_payload()

                # Gemini profile requires project-level access; gracefully fallback to Chirp/default.
                if response.status_code != 200 and model_name:
                    if fallback_voice_name:
                        fallback_payload = {
                            "input": {"text": processed_text},
                            "voice": {"languageCode": language_code, "name": fallback_voice_name},
                            "audioConfig": {
                                "audioEncoding": "LINEAR16",
                                "sampleRateHertz": 24000,
                                "speakingRate": max(0.25, min(4.0, float(speed))),
                            },
                        }
                        fallback_response, fallback_auth_mode = await self._request_with_auth_fallback(
                            client,
                            "POST",
                            url,
                            payload=fallback_payload,
                        )
                        if fallback_response is not None and fallback_response.status_code == 200:
                            response = fallback_response
                            auth_mode = fallback_auth_mode
                            resolved_voice_name = fallback_voice_name
                            model_name = None
                            fallback_used = True
                            logger.warning(
                                "[WARN] Google TTS fallback applied: requested_model=%s requested_voice=%s fallback_voice=%s",
                                requested_model_name or "-",
                                voice_name or "-",
                                fallback_voice_name,
                            )
                        else:
                            logger.warning(
                                "[WARN] Google TTS Gemini fallback failed: primary=%s fallback=%s",
                                response.status_code,
                                fallback_response.status_code if fallback_response is not None else "n/a",
                            )

                if response.status_code != 200:
                    log_fn = logger.warning if response.status_code in {400, 401, 403} else logger.error
                    log_fn("[ERROR] Google TTS error %s: %s", response.status_code, response.text)
                    response_data = {}
                    try:
                        response_data = response.json()
                    except Exception:
                        response_data = {}
                    return _google_error_payload(response.status_code, response.text, response_data)

                data = response.json()
                audio_b64 = data.get("audioContent")
                if not audio_b64:
                    return {"success": False, "error": "No audioContent in response"}

                audio_bytes = base64.b64decode(audio_b64)

            timestamp = int(time.time() * 1000)
            output_wav = self.temp_dir / f"gcloud_tts_{timestamp}.wav"
            try:
                audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="wav")
            except Exception:
                # Fallback parser for raw PCM payloads (defensive path).
                audio = AudioSegment(
                    data=audio_bytes,
                    sample_width=2,
                    frame_rate=24000,
                    channels=1,
                )

            if volume_level != 50.0:
                db_change = ((volume_level - 50) / 50) * 10
                audio = audio + db_change

            # Add short tail silence to avoid abrupt cut
            audio = audio + AudioSegment.silent(duration=300)

            audio.export(
                str(output_wav),
                format="wav",
                parameters=["-ar", "24000", "-ac", "1"]
            )

            return {
                "success": True,
                "audio_path": str(output_wav.resolve()),
                "voice": resolved_voice_name,
                "language_code": language_code,
                "auth_mode": auth_mode,
                "requested_model": requested_model_name,
                "fallback_used": fallback_used,
            }

        except Exception as exc:
            logger.exception("[ERROR] Google TTS synthesis failed")
            return {
                "success": False,
                "error": str(exc),
                "hint": "Google TTS request failed due to transport/internal error",
                "status_code": None,
            }

    async def list_voices(self, language_code: Optional[str] = None) -> Dict[str, Any]:
        """Fetch available voices from Google Cloud TTS (cached)."""
        cache_key = language_code or "all"
        cached = _VOICES_CACHE.get(cache_key)
        now = time.time()
        if cached and cached[0] > now:
            return {"success": True, "voices": cached[1], "cached": True}

        url = "https://texttospeech.googleapis.com/v1/voices"
        params: Dict[str, Any] = {}
        if language_code:
            params["languageCode"] = language_code

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response, auth_mode = await self._request_with_auth_fallback(
                    client,
                    "GET",
                    url,
                    params=params,
                )
                if response is None:
                    payload = _google_auth_not_configured_payload()
                    return {
                        **payload,
                        "voices": [],
                        "cached": False,
                    }

                if response.status_code != 200:
                    log_fn = logger.warning if response.status_code in {400, 401, 403} else logger.error
                    log_fn("[ERROR] Google TTS voices error %s: %s", response.status_code, response.text)
                    response_data = {}
                    try:
                        response_data = response.json()
                    except Exception:
                        response_data = {}
                    payload = _google_error_payload(response.status_code, response.text, response_data)
                    return {
                        **payload,
                        "voices": [],
                        "cached": False,
                    }

                data = response.json()
                voices_raw = data.get("voices", [])
                voices = _sorted_voices(
                    _filter_gemini_and_chirp_voices(
                        _add_gemini_aliases(voices_raw)
                    )
                )

            _VOICES_CACHE[cache_key] = (now + _VOICES_CACHE_TTL, voices)
            return {"success": True, "voices": voices, "cached": False, "auth_mode": auth_mode}
        except Exception as exc:
            logger.exception("[ERROR] Google TTS voices fetch failed")
            return {
                "success": False,
                "error": str(exc),
                "hint": "Failed to request Google voices due to transport/internal error",
                "voices": [],
                "cached": False,
                "status_code": None,
            }


_google_cloud_tts_instance: Optional[GoogleCloudTTS] = None


def get_google_cloud_tts() -> GoogleCloudTTS:
    """Singleton accessor for GoogleCloudTTS."""
    global _google_cloud_tts_instance
    if _google_cloud_tts_instance is None:
        _google_cloud_tts_instance = GoogleCloudTTS()
    return _google_cloud_tts_instance

