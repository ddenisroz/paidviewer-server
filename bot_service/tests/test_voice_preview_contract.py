import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx
import pytest

from api.tts import voices_routes


class _FakeVoiceService:
    db = object()

    async def get_voice_info(self, voice_id: int, provider: str):
        assert voice_id == 1
        assert provider == "f5"
        return {"id": 1, "name": "voice_one", "owner_id": 1, "is_global": False}


@pytest.mark.asyncio
async def test_f5_voice_preview_localizes_provider_audio_to_bot_service(monkeypatch):
    class _FakeAsyncClient:
        def __init__(self, timeout=None, **kwargs):
            _ = (timeout, kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            _ = (args, kwargs)
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "audio_url": "/api/tts/audio/provider-preview.wav",
                    "voice": "female_1",
                    "selected_voice": "female_1",
                    "tts_type": "ai_f5",
                },
            )

        async def get(self, *args, **kwargs):
            _ = (args, kwargs)
            return httpx.Response(
                200,
                content=b"RIFFfakewav",
                headers={"content-type": "audio/wav"},
            )

    with tempfile.TemporaryDirectory(prefix="voice_preview_localized_") as temp_dir:
        temp_root = Path(temp_dir)

        monkeypatch.setattr(voices_routes.httpx, "AsyncClient", _FakeAsyncClient)
        monkeypatch.setattr(voices_routes, "_provider_base_url", lambda provider: "http://localhost:8011")
        monkeypatch.setattr(voices_routes, "_provider_upstream_params", lambda provider, extra_params=None: extra_params or {})
        monkeypatch.setattr(voices_routes, "_tts_auth_headers", lambda provider: {})
        monkeypatch.setattr(voices_routes.settings, "backend_url", "http://localhost:8000")
        monkeypatch.setattr(voices_routes, "TEMP_DIR", temp_root)

        result = await voices_routes.test_voice(
            voice_id=1,
            payload={"text": "Привет"},
            current_user={"id": 1},
            service=_FakeVoiceService(),
            provider="f5",
        )

        assert result["success"] is True
        assert result["audio_url"].startswith("http://localhost:8000/api/tts/audio/preview_f5_")
        saved_files = list((temp_root / "tts_audio").glob("preview_f5_*"))
        assert saved_files
        assert Path(urlparse(result["audio_url"]).path).name in {path.name for path in saved_files}
