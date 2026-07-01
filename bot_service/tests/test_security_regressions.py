import pytest
import json
import sys
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

_f5_root_env = (os.getenv("F5_TTS_REPO_ROOT") or "").strip()
F5_TTS_ROOT = Path(_f5_root_env) if _f5_root_env else (Path(__file__).resolve().parents[2] / "F5_tts")
_HAS_F5_TEST_MODULES = False
_F5_TEST_SKIP_REASON = "F5 service sources are unavailable for cross-repo security regression tests."
tts_media_router = None
tts_control_api = None

if F5_TTS_ROOT.exists():
    try:
        if str(F5_TTS_ROOT) not in sys.path:
            sys.path.insert(0, str(F5_TTS_ROOT))

        _f5_auth_spec = importlib.util.spec_from_file_location("f5_tts_auth", F5_TTS_ROOT / "auth.py")
        if _f5_auth_spec is None or _f5_auth_spec.loader is None:
            raise ImportError("Unable to load auth.py from F5 service repository")
        _f5_auth = importlib.util.module_from_spec(_f5_auth_spec)
        _f5_auth_spec.loader.exec_module(_f5_auth)

        _prev_auth = sys.modules.get("auth")
        try:
            sys.modules["auth"] = _f5_auth
            from routers import media as tts_media_router
            import tts_control_api
            _HAS_F5_TEST_MODULES = True
        finally:
            if _prev_auth is not None:
                sys.modules["auth"] = _prev_auth
            else:
                sys.modules.pop("auth", None)
    except Exception as exc:
        _F5_TEST_SKIP_REASON = f"Failed to import F5 service modules: {exc}"
else:
    _F5_TEST_SKIP_REASON = (
        "F5 service source path is not found. Set F5_TTS_REPO_ROOT to run cross-repo security tests."
    )

from fastapi import HTTPException
from fastapi import Response
from starlette.requests import Request

from middleware.csrf_protection import CSRFProtectionMiddleware
from services.voice_management_service import VoiceManagementService
from core.exception_handlers import http_exception_handler
from api.errors_api import _redact_sensitive, _serialize_safe_payload, report_frontend_error
from api.session_api import get_active_channels, get_active_sessions
from api import stream_history_api
from api import obs_integration_api
from api import platforms_api
from api import bot_control_api
from api import active_channels_api
from api import donationalerts_api
from api import memealerts_api
from api import memealerts_proxy
from api import auth_api
from api import system_api
from api import session_api
from api import chat_analysis_api
from api import vk_api as vk_api_module
from api import monitoring_api
from api import dashboard_api
from api import additional_api
from api import stream_info_api
from api.admin import users as admin_users_api
from api.admin import dashboard as admin_dashboard_api
from api.admin import system as admin_system_api
from api.drops import webhooks_routes as drops_webhooks_routes
from api.tts import settings_routes as tts_settings_routes
from api.tts import local_routes as tts_local_routes
from api.youtube import routes as youtube_routes
from auth import donationalerts_auth
from services.psychology_service import PsychologyService
from services import psychology_service as psychology_service_module
from services.database_maintenance.database_backup_service import DatabaseBackupService
from services.advanced_rate_limiter import AdvancedRateLimiter


def _dummy_asgi_app(scope, receive, send):
    return None


def test_csrf_exempt_path_does_not_match_prefix_collisions():
    middleware = CSRFProtectionMiddleware(_dummy_asgi_app, secret_key="test-secret")

    assert middleware._is_exempt_path("/auth/twitch")
    assert middleware._is_exempt_path("/auth/twitch/callback")
    assert not middleware._is_exempt_path("/auth/twitchevil")
    assert not middleware._is_exempt_path("/docs-hack")


def test_donationalerts_webhook_secret_rejects_invalid_secret(monkeypatch):
    monkeypatch.setattr(
        drops_webhooks_routes,
        "settings",
        SimpleNamespace(donationalerts_webhook_secret="expected-secret", is_production=False),
    )

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/drops/donationalerts/webhook",
        "headers": [(b"x-donationalerts-secret", b"wrong-secret")],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    request = Request(scope)

    with pytest.raises(HTTPException) as exc_info:
        drops_webhooks_routes._verify_donationalerts_webhook_secret(request)
    assert exc_info.value.status_code == 403


def test_donationalerts_webhook_secret_accepts_query_secret(monkeypatch):
    monkeypatch.setattr(
        drops_webhooks_routes,
        "settings",
        SimpleNamespace(donationalerts_webhook_secret="expected-secret", is_production=False),
    )

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/drops/donationalerts/webhook",
        "headers": [],
        "query_string": b"secret=expected-secret",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    request = Request(scope)

    # Should not raise for valid secret in query.
    drops_webhooks_routes._verify_donationalerts_webhook_secret(request)


def test_advanced_rate_limiter_prefers_forwarded_ip():
    limiter = AdvancedRateLimiter()
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/test",
        "headers": [(b"x-forwarded-for", b"203.0.113.10, 10.0.0.1")],
        "query_string": b"",
        "client": ("10.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    request = Request(scope)

    assert limiter._get_identifier(request=request) == "ip:203.0.113.10"


@pytest.mark.asyncio
async def test_voice_upload_hides_internal_magic_error(db, monkeypatch):
    service = VoiceManagementService(db)

    from validators import file_validators

    monkeypatch.setattr(file_validators.FileValidator, "validate_filename", staticmethod(lambda *_: (True, "")))
    monkeypatch.setattr(file_validators.FileValidator, "validate_audio_metadata", staticmethod(lambda *_: (True, "")))
    monkeypatch.setattr(file_validators.FileValidator, "validate_size_limit", staticmethod(lambda *_: (True, "")))
    monkeypatch.setattr(
        file_validators,
        "validate_file_magic_number",
        lambda *_: (False, "Invalid file content type: application/x-msdownload. File may be malicious."),
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.upload_user_voice(
            user_id=1,
            name="voice",
            filename="voice.wav",
            content=b"not-audio",
            content_type="audio/wav",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid file content. File may be malicious or corrupted."


@pytest.mark.asyncio
async def test_http_exception_handler_masks_5xx_detail():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/test",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    request = Request(scope)
    response = await http_exception_handler(
        request,
        HTTPException(status_code=500, detail="Database connection failed: secret details"),
    )
    payload = json.loads(response.body.decode("utf-8"))
    assert response.status_code == 500
    assert isinstance(payload["detail"], str)
    assert payload["detail"]
    assert payload["detail"] != "Database connection failed: secret details"
    assert "Database connection failed" not in payload["detail"]


@pytest.mark.asyncio
async def test_http_exception_handler_keeps_4xx_detail():
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/test",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    request = Request(scope)
    response = await http_exception_handler(
        request,
        HTTPException(status_code=400, detail="Bad request"),
    )
    payload = json.loads(response.body.decode("utf-8"))
    assert response.status_code == 400
    assert payload["detail"] == "Bad request"


def test_error_payload_redacts_sensitive_fields():
    payload = {
        "message": "boom",
        "token": "abc",
        "nested": {
            "Authorization": "Bearer secret",
            "password": "123",
            "safe": "ok",
        },
        "items": [{"refresh_token": "r1"}, {"x": 1}],
    }

    redacted = _redact_sensitive(payload)

    assert redacted["token"] == "***redacted***"
    assert redacted["nested"]["Authorization"] == "***redacted***"
    assert redacted["nested"]["password"] == "***redacted***"
    assert redacted["nested"]["safe"] == "ok"
    assert redacted["items"][0]["refresh_token"] == "***redacted***"


def test_error_payload_serialization_truncates_large_payload():
    payload = {"token": "secret-token", "data": "x" * 10000}
    serialized = _serialize_safe_payload(payload)
    assert "***redacted***" in serialized
    assert "secret-token" not in serialized
    assert serialized.endswith("...<truncated>")
    assert len(serialized) <= 4020


@pytest.mark.asyncio
async def test_session_admin_endpoints_require_admin():
    with pytest.raises(HTTPException) as e2:
        await get_active_channels(user={"id": 10, "role": "user", "is_admin": False}, db=None)
    assert e2.value.status_code == 403

    with pytest.raises(HTTPException) as e3:
        await get_active_sessions(user={"id": 10, "role": "user", "is_admin": False}, db=None)
    assert e3.value.status_code == 403


@pytest.mark.asyncio
async def test_frontend_error_report_rejects_large_content_length():
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/errors/report",
        "headers": [(b"content-length", b"999999")],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    request = Request(scope)
    with pytest.raises(HTTPException) as exc_info:
        await report_frontend_error(request)
    assert exc_info.value.status_code == 413


@pytest.mark.asyncio
async def test_frontend_error_report_rejects_large_body_without_content_length():
    large_body = b"x" * (17 * 1024)
    sent = {"done": False}

    async def receive():
        if sent["done"]:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent["done"] = True
        return {"type": "http.request", "body": large_body, "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/errors/report",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    request = Request(scope, receive=receive)
    with pytest.raises(HTTPException) as exc_info:
        await report_frontend_error(request)
    assert exc_info.value.status_code == 413


@pytest.mark.asyncio
async def test_frontend_error_report_read_body_limited_stops_on_overflow():
    async def receive_gen():
        chunks = [b"a" * 8000, b"b" * 9000]
        for idx, chunk in enumerate(chunks):
            yield {"type": "http.request", "body": chunk, "more_body": idx < len(chunks) - 1}
        while True:
            yield {"type": "http.request", "body": b"", "more_body": False}

    gen = receive_gen()

    async def receive():
        return await gen.__anext__()

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/errors/report",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    request = Request(scope, receive=receive)

    with pytest.raises(HTTPException) as exc_info:
        await report_frontend_error(request)
    assert exc_info.value.status_code == 413


@pytest.mark.asyncio
async def test_stream_history_is_scoped_to_current_user(monkeypatch):
    observed = {}

    class FakeRepo:
        def __init__(self, _db):
            pass

        def get_paginated(self, **kwargs):
            observed.update(kwargs)
            return ([], 0)

    monkeypatch.setattr(stream_history_api, "ChatMessageRepository", FakeRepo)

    result = await stream_history_api.get_stream_history(
        page=1,
        limit=10,
        channel_name=None,
        platform=None,
        user={"id": 42},
        db=None,
    )

    assert result["success"] is True
    assert observed["user_id"] == 42


@pytest.mark.asyncio
async def test_stream_stats_is_scoped_to_current_user(monkeypatch):
    observed = {}

    class FakeRepo:
        def __init__(self, _db):
            pass

        def get_stats(self, **kwargs):
            observed.update(kwargs)
            return {"total_messages": 0, "messages_24h": 0, "unique_viewers": 0}

    monkeypatch.setattr(stream_history_api, "ChatMessageRepository", FakeRepo)

    result = await stream_history_api.get_stream_stats(
        channel_name=None,
        platform=None,
        user={"id": 99},
        db=None,
    )

    assert result["success"] is True
    assert observed["user_id"] == 99


@pytest.mark.asyncio
async def test_stream_history_preserves_http_exceptions():
    with pytest.raises(HTTPException) as exc_info:
        await stream_history_api.get_stream_history(
            page=1,
            limit=10,
            channel_name=None,
            platform=None,
            user={},
            db=None,
        )
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_stream_history_returns_500_on_repository_failure(monkeypatch):
    class BrokenRepo:
        def __init__(self, _db):
            pass

        def get_paginated(self, **_kwargs):
            raise RuntimeError("db exploded")

    monkeypatch.setattr(stream_history_api, "ChatMessageRepository", BrokenRepo)

    with pytest.raises(HTTPException) as exc_info:
        await stream_history_api.get_stream_history(
            page=1,
            limit=10,
            channel_name=None,
            platform=None,
            user={"id": 1},
            db=None,
        )
    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_stream_stats_returns_500_on_repository_failure(monkeypatch):
    class BrokenRepo:
        def __init__(self, _db):
            pass

        def get_stats(self, **_kwargs):
            raise RuntimeError("db exploded")

    monkeypatch.setattr(stream_history_api, "ChatMessageRepository", BrokenRepo)

    with pytest.raises(HTTPException) as exc_info:
        await stream_history_api.get_stream_stats(
            channel_name=None,
            platform=None,
            user={"id": 1},
            db=None,
        )
    assert exc_info.value.status_code == 500


def test_psychology_service_scopes_queries_to_owner_user(monkeypatch):
    observed = {}

    class FakeRepo:
        def __init__(self, _db):
            pass

        def get_recent_by_author_in_channel(self, **kwargs):
            observed["channel"] = kwargs
            return []

        def get_recent_by_author(self, **kwargs):
            observed["global"] = kwargs
            return []

    monkeypatch.setattr(psychology_service_module, "ChatMessageRepository", FakeRepo)
    service = PsychologyService(db=None)
    service._get_user_messages(
        owner_user_id=123,
        username="viewer1",
        platform="twitch",
        channel_name="channel1",
        channel_limit=5,
        global_limit=7,
    )

    assert observed["channel"]["user_id"] == 123
    assert observed["global"]["user_id"] == 123


@pytest.mark.asyncio
async def test_generate_obs_url_does_not_fallback_to_ephemeral_token(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise RuntimeError("db write failed")

    monkeypatch.setattr(obs_integration_api, "get_or_create_obs_token", _boom)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/tts/generate-obs-url",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    request = Request(scope)

    with pytest.raises(HTTPException) as exc_info:
        await obs_integration_api.generate_obs_url(
            request=request,
            user={"id": 7},
            db=type("DummyDb", (), {"rollback": lambda self: None})(),
        )
    assert exc_info.value.status_code == 500


def test_get_or_create_obs_token_requires_existing_user(monkeypatch):
    class DummyRepo:
        def __init__(self, _db):
            pass

        def get_by_id(self, _user_id):
            return None

    monkeypatch.setattr(obs_integration_api, "UserRepository", DummyRepo)

    with pytest.raises(HTTPException) as exc_info:
        obs_integration_api.get_or_create_obs_token(db=None, user_id=999)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.skipif(not _HAS_F5_TEST_MODULES, reason=_F5_TEST_SKIP_REASON)
async def test_tts_media_delete_returns_404_for_missing_file(monkeypatch):
    monkeypatch.setattr(tts_media_router, "_sanitize_voice_name", lambda value: "missing.wav")
    monkeypatch.setattr(
        tts_media_router,
        "_resolve_under_base",
        lambda _base, _name: __import__("pathlib").Path("definitely_missing_file.wav"),
    )

    with pytest.raises(HTTPException) as exc_info:
        await tts_media_router.delete_audio_file(
            voice_name="missing",
            current_user={"role": "admin"},
        )
    assert exc_info.value.status_code == 404


def test_backup_restore_rejects_path_traversal_filename():
    service = DatabaseBackupService()
    result = service.restore_from_backup_file("backup_../../secret.sql")
    assert result["success"] is False
    assert result["error"] == "Invalid file path"


def test_backup_restore_rejects_nested_path_filename():
    service = DatabaseBackupService()
    result = service.restore_from_backup_file("backup_20250101_010101.sql/evil.sql")
    assert result["success"] is False
    assert result["error"] == "Invalid file path"


@pytest.mark.asyncio
async def test_platforms_config_returns_500_on_failure(monkeypatch):
    monkeypatch.setattr(platforms_api.platform_registry, "get_configs", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(HTTPException) as exc_info:
        await platforms_api.get_platforms_config()
    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_platforms_list_returns_500_on_failure(monkeypatch):
    monkeypatch.setattr(platforms_api.platform_registry, "get_all", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(HTTPException) as exc_info:
        await platforms_api.list_platforms()
    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_bot_control_get_status_returns_500_on_internal_error(monkeypatch):
    monkeypatch.setattr(bot_control_api, "_get_user_or_404", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(HTTPException) as exc_info:
        await bot_control_api.get_bot_status(
            user={"id": 1},
            db=None,
            bot_service=object(),
        )
    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_active_channels_returns_500_on_repository_failure(monkeypatch):
    class BrokenRepo:
        def __init__(self, _db):
            pass

        def get_with_chat_enabled(self):
            raise RuntimeError("db fail")

    monkeypatch.setattr(active_channels_api, "UserSettingsRepository", BrokenRepo)

    with pytest.raises(HTTPException) as exc_info:
        await active_channels_api.get_active_channels(
            user={"id": 1},
            db=None,
        )
    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_donationalerts_connect_requires_authentication():
    with pytest.raises(HTTPException) as exc_info:
        await donationalerts_api.connect_donationalerts(user=None, db=None)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_memealerts_status_returns_500_on_token_repo_failure(monkeypatch):
    class BrokenTokenRepo:
        def __init__(self, _db):
            pass

        def get_by_user_and_platform(self, *_args, **_kwargs):
            raise RuntimeError("db fail")

    monkeypatch.setattr(memealerts_api, "UserTokenRepository", BrokenTokenRepo)
    with pytest.raises(HTTPException) as exc_info:
        await memealerts_api.get_memealerts_status(user={"id": 1}, db=None)
    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_session_disconnect_channel_returns_404_when_channel_missing(monkeypatch):
    class DummyService:
        def __init__(self, _db):
            pass

        def disconnect_channel(self, _channel_name, _user_id):
            return False

    monkeypatch.setattr(session_api, "SessionService", DummyService)
    with pytest.raises(HTTPException) as exc_info:
        await session_api.disconnect_channel(
            channel_name="missing-channel",
            user={"id": 1, "role": "admin", "is_admin": True},
            db=None,
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_system_metrics_returns_500_on_failure(monkeypatch):
    import types
    import sys

    fake_mod = types.ModuleType("utils.enhanced_logger")
    fake_mod.get_system_metrics = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    monkeypatch.setitem(sys.modules, "utils.enhanced_logger", fake_mod)

    with pytest.raises(HTTPException) as exc_info:
        await system_api.get_metrics()
    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
@pytest.mark.skipif(not _HAS_F5_TEST_MODULES, reason=_F5_TEST_SKIP_REASON)
async def test_tts_control_returns_401_for_invalid_auth_payload():
    with pytest.raises(HTTPException) as exc_info:
        await tts_control_api.enable_tts(current_user={"id": "not-int"})
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_chat_analysis_raises_500_when_service_returns_empty(monkeypatch):
    class DummyUserRepo:
        def __init__(self, _db):
            pass

        def get_by_id(self, _user_id):
            return type("User", (), {"twitch_username": "owner", "vk_username": None, "vk_channel_name": None})()

    class DummyPsychService:
        def __init__(self, _db):
            pass

        async def analyze_user_psychology(self, **_kwargs):
            return None

    monkeypatch.setattr(chat_analysis_api, "UserRepository", DummyUserRepo)
    monkeypatch.setattr(chat_analysis_api, "PsychologyService", DummyPsychService)

    payload = chat_analysis_api.ChatAnalysisRequest(username="viewer", platform="twitch")
    with pytest.raises(HTTPException) as exc_info:
        await chat_analysis_api.analyze_chat_user(
            payload=payload,
            user={"id": 1},
            db=None,
        )
    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_vk_categories_returns_503_when_no_token(monkeypatch):
    class DummyTokenRepo:
        def __init__(self, _db):
            pass

        def get_by_user_and_platform(self, *_args, **_kwargs):
            return None

        def get_first_by_platform(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(vk_api_module, "UserTokenRepository", DummyTokenRepo, raising=False)
    # Fallback import path inside endpoint
    import repositories.user_token_repository as token_repo_module
    monkeypatch.setattr(token_repo_module, "UserTokenRepository", DummyTokenRepo)

    with pytest.raises(HTTPException) as exc_info:
        await vk_api_module.get_vk_categories(search="", current_user={"id": 1, "session_id": "s"}, db=None)
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_vk_stream_info_returns_normalized_payload(monkeypatch):
    from services.stream_info_service import StreamInfoService

    async def _fake_get_stream_info(self, _user_id, _platform_name, _session_id=None):
        return {"title": "Offline", "category": {"name": "Just Chatting", "title": "Just Chatting"}}

    monkeypatch.setattr(StreamInfoService, "get_stream_info", _fake_get_stream_info)

    response = await vk_api_module.get_vk_stream_info(
        current_user={"id": 1, "session_id": "s"},
        db=None,
    )
    assert response.status_code == 200
    assert json.loads(response.body) == {
        "data": {
            "title": "Offline",
            "category": {
                "name": "Just Chatting",
                "title": "Just Chatting",
            },
        }
    }


@pytest.mark.asyncio
async def test_monitoring_clear_cache_requires_admin():
    with pytest.raises(HTTPException) as exc_info:
        await monitoring_api.clear_cache(user={"id": 1, "role": "user", "is_admin": False})
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_monitoring_cleanup_cache_requires_admin():
    with pytest.raises(HTTPException) as exc_info:
        await monitoring_api.cleanup_expired_cache(user={"id": 1, "role": "user", "is_admin": False})
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_dashboard_init_raises_500_on_internal_error(monkeypatch):
    class BrokenService:
        def __init__(self, _db):
            pass

        async def get_dashboard_init_data(self, _current_user):
            raise RuntimeError("boom")

    monkeypatch.setattr(dashboard_api, "DashboardService", BrokenService)

    with pytest.raises(HTTPException) as exc_info:
        await dashboard_api.get_dashboard_init(current_user={"id": 1}, db=None)
    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_additional_get_integrations_raises_500_on_failure(monkeypatch):
    async def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(additional_api.integration_management_service, "get_user_integrations", _boom)

    with pytest.raises(HTTPException) as exc_info:
        await additional_api.get_integrations(user={"id": 1}, db=None)
    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_stream_info_twitch_raises_500_on_internal_error():
    class BrokenService:
        async def get_stream_info(self, *_args, **_kwargs):
            raise RuntimeError("boom")

    with pytest.raises(HTTPException) as exc_info:
        await stream_info_api.get_twitch_stream_info(
            user={"id": 1, "session_id": "s"},
            service=BrokenService(),
        )
    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_stream_update_platform_raises_409_on_failed_update():
    class DummyService:
        def __init__(self):
            self.last_error_by_platform = {"twitch": "update failed"}

        async def update_stream(self, *_args, **_kwargs):
            return False

    with pytest.raises(HTTPException) as exc_info:
        await stream_info_api.update_platform_stream(
            platform_name="twitch",
            title="new",
            category_id=None,
            user={"id": 1, "session_id": "s"},
            service=DummyService(),
        )
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_stream_update_raises_409_with_failure_details():
    class _PlatformUpdate:
        def __init__(self, title=None, category_id=None, category=None):
            self.title = title
            self.category_id = category_id
            self.category = category

    class _Request:
        def __init__(self):
            self.twitch = _PlatformUpdate(title="new title")
            self.vk = None

    class DummyService:
        def __init__(self):
            self.last_error_by_platform = {"twitch": "update failed"}

        async def update_stream(self, *_args, **_kwargs):
            return False

        async def get_stream_info(self, *_args, **_kwargs):
            return {}

    with pytest.raises(HTTPException) as exc_info:
        await stream_info_api.update_stream(
            request=_Request(),
            user={"id": 1, "session_id": "s"},
            service=DummyService(),
        )
    assert exc_info.value.status_code == 409
    assert isinstance(exc_info.value.detail, dict)
    assert "failed_platforms" in exc_info.value.detail


@pytest.mark.asyncio
async def test_admin_remove_whitelist_rejects_invalid_platform():
    with pytest.raises(HTTPException) as exc_info:
        await admin_users_api.remove_from_whitelist(
            username="user1",
            platform="invalid",
            user={"id": 1, "role": "admin", "is_admin": True},
            db=None,
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_admin_dashboard_stats_returns_500_on_internal_error(monkeypatch):
    monkeypatch.setattr(admin_dashboard_api, "get_admin_stats_service", lambda _db: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(HTTPException) as exc_info:
        await admin_dashboard_api.get_dashboard_stats(
            user={"id": 1, "role": "admin", "is_admin": True},
            db=None,
        )
    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_admin_system_tts_restart_returns_502_when_unhealthy(monkeypatch):
    class DummyResponse:
        status_code = 503

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *_args, **_kwargs):
            return DummyResponse()

    monkeypatch.setattr(admin_system_api.httpx, "AsyncClient", lambda *args, **kwargs: DummyClient())

    with pytest.raises(HTTPException) as exc_info:
        await admin_system_api.restart_tts_engine(
            user={"id": 1, "role": "admin", "is_admin": True},
        )
    assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_tts_add_filtered_word_returns_409_when_duplicate():
    class DummyService:
        async def add_filtered_word(self, *_args, **_kwargs):
            return False

    with pytest.raises(HTTPException) as exc_info:
        await tts_settings_routes.add_filtered_word(
            request=type("Req", (), {"word": "spam", "platform": "twitch"})(),
            user={"id": 1},
            service=DummyService(),
        )
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_local_tts_toggle_returns_503_when_health_fails(monkeypatch):
    class DummyUser:
        pass

    class DummyConfig:
        def __init__(self):
            self.use_local = True
            self.endpoint_url = "http://localhost:8001"
            self.api_key = None

    class DummyRepo:
        def __init__(self, _db):
            pass

        def get_user_by_id(self, _user_id):
            return DummyUser()

        def is_user_whitelisted(self, _db_user, _login_platform):
            return True

        def get_by_user_id(self, _user_id, provider=None):
            return DummyConfig()

        def toggle_use_local(self, config):
            config.use_local = True
            return config

        def disable_local(self, config):
            config.use_local = False

    async def _unhealthy(*_args, **_kwargs):
        return {"healthy": False}

    monkeypatch.setattr(tts_local_routes, "LocalTTSRepository", DummyRepo)
    monkeypatch.setattr(tts_local_routes, "check_local_tts_health", _unhealthy)

    with pytest.raises(HTTPException) as exc_info:
        await tts_local_routes.toggle_local_tts(
            user={"id": 1, "login_platform": "twitch"},
            db=None,
        )
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_local_tts_test_connection_returns_504_on_timeout(monkeypatch):
    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *_args, **_kwargs):
            raise tts_local_routes.httpx.TimeoutException("timeout")

    monkeypatch.setattr(tts_local_routes.httpx, "AsyncClient", lambda *args, **kwargs: DummyClient())
    req = type("Req", (), {"endpoint_url": "http://localhost:8001", "api_key": None, "provider": "f5"})()

    with pytest.raises(HTTPException) as exc_info:
        await tts_local_routes.test_local_tts_connection(request=req, user={"id": 1}, db=None)
    assert exc_info.value.status_code == 504


@pytest.mark.asyncio
async def test_local_tts_test_connection_rejects_disallowed_endpoint(monkeypatch):
    monkeypatch.setattr(tts_local_routes, "normalize_local_tts_endpoint_url", lambda _url: (_ for _ in ()).throw(ValueError("blocked")))
    req = type("Req", (), {"endpoint_url": "http://evil.example:8001", "api_key": None, "provider": "f5"})()

    with pytest.raises(HTTPException) as exc_info:
        await tts_local_routes.test_local_tts_connection(request=req, user={"id": 1}, db=None)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_local_tts_test_connection_returns_502_on_connect_error(monkeypatch):
    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *_args, **_kwargs):
            raise tts_local_routes.httpx.ConnectError("connect failed")

    monkeypatch.setattr(tts_local_routes.httpx, "AsyncClient", lambda *args, **kwargs: DummyClient())
    req = type("Req", (), {"endpoint_url": "http://localhost:8001", "api_key": None, "provider": "f5"})()

    with pytest.raises(HTTPException) as exc_info:
        await tts_local_routes.test_local_tts_connection(request=req, user={"id": 1}, db=None)
    assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_tts_settings_get_global_voices_returns_502_on_upstream_connect_error(monkeypatch):
    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *_args, **_kwargs):
            raise tts_settings_routes.httpx.ConnectError("connect failed")

    monkeypatch.setattr(tts_settings_routes.httpx, "AsyncClient", lambda *args, **kwargs: DummyClient())

    with pytest.raises(HTTPException) as exc_info:
        await tts_settings_routes.get_global_voices(user={"id": 1})
    assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_tts_settings_get_user_voices_returns_504_on_upstream_timeout(monkeypatch):
    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *_args, **_kwargs):
            raise tts_settings_routes.httpx.TimeoutException("timeout")

    monkeypatch.setattr(tts_settings_routes.httpx, "AsyncClient", lambda *args, **kwargs: DummyClient())

    with pytest.raises(HTTPException) as exc_info:
        await tts_settings_routes.get_user_voices(target_user_id=1, user={"id": 1, "role": "user", "is_admin": False})
    assert exc_info.value.status_code == 504


@pytest.mark.asyncio
async def test_tts_settings_get_global_voices_returns_500_on_unexpected_error(monkeypatch):
    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *_args, **_kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(tts_settings_routes.httpx, "AsyncClient", lambda *args, **kwargs: DummyClient())

    with pytest.raises(HTTPException) as exc_info:
        await tts_settings_routes.get_global_voices(user={"id": 1})
    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_tts_settings_get_user_voices_returns_500_on_unexpected_error(monkeypatch):
    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *_args, **_kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(tts_settings_routes.httpx, "AsyncClient", lambda *args, **kwargs: DummyClient())

    with pytest.raises(HTTPException) as exc_info:
        await tts_settings_routes.get_user_voices(target_user_id=1, user={"id": 1, "role": "user", "is_admin": False})
    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_youtube_get_next_video_returns_404_when_queue_empty(monkeypatch):
    monkeypatch.setattr(youtube_routes.queue_service, "get_next_video", lambda *_args, **_kwargs: None)

    with pytest.raises(HTTPException) as exc_info:
        await youtube_routes.get_next_video(user={"id": 1}, db=None)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_youtube_skip_next_returns_404_when_queue_empty(monkeypatch):
    monkeypatch.setattr(youtube_routes.queue_service, "get_queue", lambda *_args, **_kwargs: [])

    with pytest.raises(HTTPException) as exc_info:
        await youtube_routes.skip_to_next_video(user={"id": 1}, db=None)
    assert exc_info.value.status_code == 404


def test_memealerts_proxy_blocks_javascript_redirect_location():
    location = memealerts_proxy._sanitize_redirect_location("javascript:alert(1)", memealerts_proxy.PROXY_PREFIX)
    assert location == memealerts_proxy.PROXY_PREFIX


def test_memealerts_proxy_blocks_external_absolute_redirect_location():
    location = memealerts_proxy._sanitize_redirect_location("https://evil.example/phish", memealerts_proxy.PROXY_PREFIX)
    assert location == memealerts_proxy.PROXY_PREFIX


def test_memealerts_proxy_blocks_crlf_redirect_location():
    location = memealerts_proxy._sanitize_redirect_location("/ok\r\nX-Injected: 1", memealerts_proxy.PROXY_PREFIX)
    assert location == memealerts_proxy.PROXY_PREFIX


def test_memealerts_proxy_allows_local_callback_redirect_for_auth():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/memealerts/proxy/api/auth/google",
        "headers": [(b"host", b"localhost")],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("localhost", 80),
        "scheme": "http",
    }
    request = Request(scope)
    location = memealerts_proxy._sanitize_redirect_location(
        "http://localhost/memealerts/callback?provider=google&accessToken=test-token",
        memealerts_proxy.PROXY_PREFIX,
        request=request,
        allow_external_auth_redirects=True,
    )
    assert location.startswith("http://localhost/memealerts/callback")


def test_memealerts_proxy_allows_provider_redirect_for_auth():
    location = memealerts_proxy._sanitize_redirect_location(
        "https://accounts.google.com/o/oauth2/v2/auth?client_id=test",
        memealerts_proxy.PROXY_PREFIX,
        allow_external_auth_redirects=True,
    )
    assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth")


def test_memealerts_proxy_auth_uses_safe_upstream_return_url():
    query = [("return_url", "https://app.local/api/memealerts/proxy/auth/redirect")]
    normalized = memealerts_proxy._build_upstream_auth_fallback_query("api/auth/twitch", query)

    assert normalized == [("return_url", memealerts_proxy.MEMEALERTS_SAFE_AUTH_RETURN_URL)]


def test_memealerts_proxy_patches_json_oauth_state_to_proxy_callback():
    proxy_return_url = "https://app.local/api/memealerts/proxy/auth/redirect"
    location = (
        "https://id.twitch.tv/oauth2/authorize?client_id=test"
        '&state={"return_url":"https://memealerts.com/auth/redirect"}'
    )

    patched = memealerts_proxy._patch_external_auth_state_location(location, proxy_return_url)
    state = parse_qs(urlparse(patched).query)["state"][0]

    assert json.loads(state)["return_url"] == proxy_return_url


def test_memealerts_proxy_patches_vk_oauth_state_to_proxy_callback():
    proxy_return_url = "https://app.local/api/memealerts/proxy/auth/redirect"
    location = (
        "https://oauth.vk.com/authorize?client_id=test"
        "&state=https%3A%2F%2Fmemealerts.com%2Fauth%2Fredirect"
    )

    patched = memealerts_proxy._patch_external_auth_state_location(location, proxy_return_url)
    state = parse_qs(urlparse(patched).query)["state"][0]

    assert state == proxy_return_url


def test_memealerts_proxy_postmessage_uses_same_origin_target():
    assert 'postMessage(data, window.location.origin)' in memealerts_proxy._INJECTED_SCRIPT


def test_memealerts_proxy_normalize_auth_query_rejects_external_return_url():
    query = [("client_id", "x"), ("return_url", "https://evil.example/cb")]
    normalized = memealerts_proxy._normalize_auth_query(
        "api/auth/login",
        query,
        proxy_return_url="https://app.local/api/memealerts/proxy/auth/redirect",
    )
    assert normalized is not None
    assert ("return_url", "https://app.local/api/memealerts/proxy/auth/redirect") in normalized


def test_memealerts_proxy_normalize_auth_query_accepts_relative_return_url():
    query = [("return_url", "/memealerts/callback")]
    normalized = memealerts_proxy._normalize_auth_query(
        "api/auth/login",
        query,
        proxy_return_url="https://app.local/api/memealerts/proxy/auth/redirect",
    )
    assert normalized is not None
    assert ("return_url", "https://app.local/memealerts/callback") in normalized


def test_memealerts_proxy_resolve_access_token_returns_decrypted(monkeypatch):
    decrypted_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.signature"
    monkeypatch.setattr(memealerts_proxy, "decrypt_token", lambda _raw: decrypted_token)
    assert memealerts_proxy._resolve_proxy_access_token("encrypted") == decrypted_token


def test_memealerts_proxy_resolve_access_token_rejects_garbage_when_decrypt_fails(monkeypatch):
    def _raise(_raw):
        raise ValueError("boom")

    monkeypatch.setattr(memealerts_proxy, "decrypt_token", _raise)
    assert memealerts_proxy._resolve_proxy_access_token("not-a-token") is None


def test_memealerts_proxy_resolve_access_token_allows_legacy_plain_token(monkeypatch):
    def _raise(_raw):
        raise ValueError("boom")

    monkeypatch.setattr(memealerts_proxy, "decrypt_token", _raise)
    legacy_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.signature"
    assert memealerts_proxy._resolve_proxy_access_token(legacy_token) == legacy_token


def test_memealerts_proxy_resolve_access_token_rejects_invalid_decrypted_format(monkeypatch):
    monkeypatch.setattr(memealerts_proxy, "decrypt_token", lambda _raw: "invalid token with spaces")
    assert memealerts_proxy._resolve_proxy_access_token("encrypted") is None


@pytest.mark.asyncio
async def test_memealerts_proxy_read_body_limited_rejects_large_payload():
    async def receive_gen():
        chunks = [b"a" * (1024 * 1024), b"b" * (1024 * 1024 + 1)]
        for idx, chunk in enumerate(chunks):
            yield {"type": "http.request", "body": chunk, "more_body": idx < len(chunks) - 1}
        while True:
            yield {"type": "http.request", "body": b"", "more_body": False}

    gen = receive_gen()

    async def receive():
        return await gen.__anext__()

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/memealerts/proxy/api/test",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    request = Request(scope, receive=receive)

    with pytest.raises(ValueError):
        await memealerts_proxy._read_proxy_body_limited(request, 2 * 1024 * 1024)


def test_donationalerts_auth_url_rejects_non_https_host():
    assert donationalerts_api._is_safe_donationalerts_auth_url("http://evil.example/oauth/authorize") is False


def test_donationalerts_auth_url_accepts_expected_domain():
    assert (
        donationalerts_api._is_safe_donationalerts_auth_url(
            "https://www.donationalerts.com/oauth/authorize?client_id=x"
        )
        is True
    )


@pytest.mark.asyncio
async def test_donationalerts_connect_sets_oauth_state_cookie(monkeypatch):
    monkeypatch.setattr(
        donationalerts_api,
        "settings",
        SimpleNamespace(
            donationalerts_client_id="client-id",
            donationalerts_redirect_uri="https://api.example.com/auth/donationalerts/callback",
            is_production=False,
        ),
    )
    response = Response()

    result = await donationalerts_api.connect_donationalerts(
        user={"id": 42},
        db=None,
        response=response,
    )

    assert result["success"] is True
    query = parse_qs(urlparse(result["auth_url"]).query)
    assert query.get("state")
    set_cookie = response.headers.get("set-cookie", "")
    assert "oauth_state_da=" in set_cookie


@pytest.mark.asyncio
async def test_donationalerts_callback_rejects_invalid_state():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/auth/donationalerts/callback",
        "headers": [(b"cookie", b"oauth_state_da=expected-state")],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    request = Request(scope)

    response = await donationalerts_auth.donationalerts_callback(
        request=request,
        code="oauth-code",
        state="wrong-state",
        db=None,
        current_user={"id": 1},
    )

    assert response.status_code in {302, 307}
    assert "auth_error=invalid_state" in response.headers.get("location", "")
    assert "oauth_state_da=" in response.headers.get("set-cookie", "")


def test_memealerts_auth_url_rejects_external_host():
    assert memealerts_api._is_safe_memealerts_auth_url("https://evil.example/auth/twitch") is False


def test_memealerts_callback_url_rejects_javascript_scheme():
    assert memealerts_api._is_safe_absolute_callback_url("javascript:alert(1)") is False


@pytest.mark.asyncio
async def test_memealerts_connect_url_prefers_proxy_callback_flow(monkeypatch):
    monkeypatch.setattr(memealerts_api.settings, "frontend_url", "https://app.local")
    monkeypatch.setattr(memealerts_api.settings, "backend_url", "https://api.local")

    result = await memealerts_api.get_memealerts_connect_url(user={"id": 1})

    assert result["flow"] == "provider_popup_callback"
    assert result["callback_url"] == "https://app.local/memealerts/callback?provider=twitch"
    assert result["auth_url"].startswith("/api/memealerts/proxy/api/auth/twitch?")
    assert "return_url=https%3A%2F%2Fapp.local%2Fmemealerts%2Fcallback%3Fprovider%3Dtwitch" in result["auth_url"]
    assert result["direct_auth_url"].startswith("https://memealerts.com/api/auth/twitch?")
    assert result["proxy_auth_url"].startswith("/api/memealerts/proxy/api/auth/twitch?")


@pytest.mark.asyncio
async def test_memealerts_connect_url_rejects_unsafe_callback_urls(monkeypatch):
    monkeypatch.setattr(memealerts_api.settings, "frontend_url", "javascript:alert(1)")
    monkeypatch.setattr(memealerts_api.settings, "backend_url", "")

    with pytest.raises(HTTPException) as exc_info:
        await memealerts_api.get_memealerts_connect_url(user={"id": 1})

    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_memealerts_connect_accepts_streamer_id_hint_for_non_jwt(monkeypatch):
    recorded: dict[str, object] = {}

    class DummyTokenRepo:
        def __init__(self, _db):
            pass

        def get_by_user_and_platform(self, _user_id, _platform):
            return None

        def upsert(self, **kwargs):
            recorded["upsert"] = kwargs

    class DummyService:
        def __init__(self, _db):
            pass

        async def validate_access_token(self, access_token, streamer_id):
            recorded["validate"] = {
                "access_token": access_token,
                "streamer_id": streamer_id,
            }
            return {"streamer_id": streamer_id}

    def _raise_invalid_token(_token):
        raise ValueError("Invalid token format")

    monkeypatch.setattr(memealerts_api, "UserTokenRepository", DummyTokenRepo)
    monkeypatch.setattr(memealerts_api, "MemeAlertsService", DummyService)
    monkeypatch.setattr(memealerts_api, "decode_memealerts_token", _raise_invalid_token)
    monkeypatch.setattr(memealerts_api, "encrypt_token", lambda value: f"enc::{value}" if value else None)

    payload = memealerts_api.ConnectMemeAlertsRequest(
        access_token="x" * 32,
        refresh_token="y" * 24,
        streamer_id="507f1f77bcf86cd799439011",
    )

    result = await memealerts_api.connect_memealerts(
        token_data=payload,
        user={"id": 7},
        db=None,
    )

    assert result["connected"] is True
    assert result["streamer_id"] == "507f1f77bcf86cd799439011"
    assert recorded["validate"] == {
        "access_token": "x" * 32,
        "streamer_id": "507f1f77bcf86cd799439011",
    }
    assert recorded["upsert"]["platform_user_id"] == "507f1f77bcf86cd799439011"


@pytest.mark.asyncio
async def test_auth_check_username_preserves_http_exception(monkeypatch):
    class DummyRepo:
        def __init__(self, _db):
            pass

        def is_username_taken(self, _username):
            raise HTTPException(status_code=429, detail="rate limited")

    monkeypatch.setattr(auth_api, "UserRepository", DummyRepo)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/auth/check-username",
        "headers": [],
        "query_string": b"username=valid_name",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }

    with pytest.raises(HTTPException) as exc_info:
        await auth_api.check_username_availability.__wrapped__(
            request=Request(scope),
            username="valid_name",
            db=None,
        )
    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_platforms_config_preserves_http_exception(monkeypatch):
    class DummyRegistry:
        def get_configs(self):
            raise HTTPException(status_code=503, detail="registry unavailable")

    monkeypatch.setattr(platforms_api, "platform_registry", DummyRegistry())

    with pytest.raises(HTTPException) as exc_info:
        await platforms_api.get_platforms_config()
    assert exc_info.value.status_code == 503
