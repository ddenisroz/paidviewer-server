import pytest
from fastapi import HTTPException

from api.tts import local_routes as tts_local_routes


@pytest.mark.asyncio
async def test_get_local_tts_config_exposes_f5_provider_contract(monkeypatch):
    class DummyRepo:
        def __init__(self, _db):
            pass

        def get_by_user_id(self, _user_id, provider=None):
            assert provider == "f5"
            return None

    monkeypatch.setattr(tts_local_routes, "LocalTTSRepository", DummyRepo)

    result = await tts_local_routes.get_local_tts_config(
        user={"id": 1},
        db=None,
        provider="f5",
    )

    assert result["configured"] is False
    assert result["provider_contract"]["upstream_parity_ready"] is True
    assert result["provider_contract"]["requires_compatibility_adapter"] is False
    assert result["provider_contract"]["managed_topology"] == "gateway_managed"
    assert result["provider_contract"]["project_hosted_direct_supported"] is True
    assert result["provider_contract"]["supports_native_strict_api_key"] is True
    assert result["provider_contract"]["supports_native_health_endpoint"] is True


@pytest.mark.asyncio
async def test_get_local_tts_config_uses_provider_mode_for_f5(monkeypatch):
    class _Config:
        id = 1
        provider = "f5"
        endpoint_url = "http://localhost:8011"
        api_key = None
        is_active = True
        is_healthy = True
        use_local = False

    class DummyRepo:
        def __init__(self, _db):
            pass

        def get_by_user_id(self, _user_id, provider=None):
            assert provider == "f5"
            return _Config()

    monkeypatch.setattr(tts_local_routes, "LocalTTSRepository", DummyRepo)
    monkeypatch.setattr(tts_local_routes, "_is_provider_local_mode", lambda _db, _user_id, _provider: True)

    result = await tts_local_routes.get_local_tts_config(
        user={"id": 1},
        db=object(),
        provider="f5",
    )

    assert result["configured"] is True
    assert result["use_local"] is True
    assert result["config"]["use_local"] is True


@pytest.mark.asyncio
async def test_f5_test_connection_surfaces_backend_health_failure(monkeypatch):
    async def _failed_health(*_args, **_kwargs):
        return {"healthy": False, "error": "HTTP 404"}

    monkeypatch.setattr(tts_local_routes, "check_local_tts_health", _failed_health)

    request = type(
        "Req",
        (),
        {"endpoint_url": "http://localhost:8011", "api_key": None, "provider": "f5"},
    )()

    with pytest.raises(HTTPException) as exc_info:
        await tts_local_routes.test_local_tts_connection(request=request, user={"id": 1}, db=None)

    assert exc_info.value.status_code == 502
    assert "http 404" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_f5_test_connection_returns_success_metadata(monkeypatch):
    async def _healthy_f5(*_args, **_kwargs):
        return {
            "healthy": True,
            "status": "healthy",
            "status_data": {"engine": "f5"},
        }

    monkeypatch.setattr(tts_local_routes, "check_local_tts_health", _healthy_f5)

    request = type(
        "Req",
        (),
        {"endpoint_url": "http://localhost:8011", "api_key": None, "provider": "f5"},
    )()

    result = await tts_local_routes.test_local_tts_connection(request=request, user={"id": 1}, db=None)

    assert result["success"] is True
    assert result["provider_contract"]["upstream_parity_ready"] is True
    assert result["warnings"] == []
    assert "successful" in result["message"].lower()
    assert result["status_data"] == {"engine": "f5"}


@pytest.mark.asyncio
async def test_toggle_local_tts_updates_f5_mode_and_mirrors_local_flag(monkeypatch):
    class _Config:
        endpoint_url = "http://localhost:8011"
        api_key = None
        use_local = False

    class DummyRepo:
        def __init__(self, _db):
            pass

        def get_by_user_id(self, _user_id, provider=None):
            assert provider == "f5"
            return _Config()

        def set_use_local(self, config, use_local: bool):
            config.use_local = use_local
            return config

    captured: dict = {}

    class _FakeTTSService:
        def __init__(self, _db):
            pass

        async def save_tts_settings(self, **kwargs):
            captured.update(kwargs)
            return {"success": True}

    async def _healthy_f5(*_args, **_kwargs):
        return {"healthy": True}

    monkeypatch.setattr(tts_local_routes, "LocalTTSRepository", DummyRepo)
    monkeypatch.setattr(tts_local_routes, "TTSService", _FakeTTSService)
    monkeypatch.setattr(tts_local_routes, "_is_provider_local_mode", lambda _db, _user_id, _provider: False)
    monkeypatch.setattr(tts_local_routes, "check_local_tts_health", _healthy_f5)

    result = await tts_local_routes.toggle_local_tts(
        user={"id": 1},
        db=object(),
        provider="f5",
    )

    assert result["success"] is True
    assert result["use_local"] is True
    assert captured["user_id"] == 1
    assert captured["f5_mode"] == "local"


@pytest.mark.asyncio
async def test_update_local_tts_voice_settings_proxies_payload(monkeypatch):
    class _Config:
        endpoint_url = "http://localhost:8011"
        api_key = "local-key"

    class DummyRepo:
        def __init__(self, _db):
            pass

        def get_by_user_id(self, _user_id, provider=None):
            assert provider == "f5"
            return _Config()

    class DummyResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"voice": {"id": 42, "reference_text": "пример", "cfg_strength": 2.5, "speed_preset": "fast"}}

    captured: dict = {}

    class DummyAsyncClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def put(self, url, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return DummyResponse()

    monkeypatch.setattr(tts_local_routes, "LocalTTSRepository", DummyRepo)
    monkeypatch.setattr(tts_local_routes.httpx, "AsyncClient", DummyAsyncClient)

    result = await tts_local_routes.update_local_tts_voice_settings(
        voice_id=42,
        settings_data={
            "reference_text": "пример",
            "cfg_strength": 2.5,
            "speed_preset": "fast",
            "ignored": "value",
        },
        provider="f5",
        user={"id": 1},
        db=object(),
    )

    assert captured["url"] == "http://localhost:8011/api/tts/user/voices/42/settings"
    assert captured["headers"]["Authorization"] == "Bearer local-key"
    assert captured["json"] == {
        "reference_text": "пример",
        "cfg_strength": 2.5,
        "speed_preset": "fast",
    }
    assert result["success"] is True
    assert result["voice"]["reference_text"] == "пример"
