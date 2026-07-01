from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi import HTTPException

from auth.oauth_handler import OAuthUserData, oauth_handler
from constants import Platform
from core.database import User, UserToken
from services.stream_info_service import StreamInfoService
from services.bot_token_validator import bot_token_validator


def test_twitch_callback_redirects_on_provider_network_error(client, monkeypatch):
    import auth.twitch_auth as twitch_auth

    monkeypatch.setattr(twitch_auth, "TWITCH_CLIENT_ID", "test-client")
    monkeypatch.setattr(twitch_auth, "TWITCH_CLIENT_SECRET", "test-secret")
    monkeypatch.setattr(twitch_auth, "TWITCH_REDIRECT_URI", "http://localhost/auth/twitch/callback")

    class BrokenClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, **kwargs):
            raise httpx.ConnectError("dns failure", request=httpx.Request(method, url))

    monkeypatch.setattr(twitch_auth.httpx, "AsyncClient", lambda *args, **kwargs: BrokenClient())

    client.cookies.set("oauth_state", "release-state")
    response = client.get(
        "/auth/twitch/callback?code=test-code&state=release-state",
        follow_redirects=False,
    )

    assert response.status_code == 307
    location = response.headers["location"]
    parsed = urlparse(location)
    query = parse_qs(parsed.query)
    assert parsed.path.endswith("/login")
    assert query["auth_error"] == ["provider_unreachable"]
    assert query["platform"] == ["twitch"]


def test_twitch_callback_preserves_provider_access_denied(client):
    response = client.get(
        "/auth/twitch/callback?error=access_denied&error_description=user_cancelled",
        follow_redirects=False,
    )

    parsed = urlparse(response.headers["location"])
    query = parse_qs(parsed.query)
    assert response.status_code == 307
    assert parsed.path.endswith("/login")
    assert query["auth_error"] == ["access_denied"]
    assert query["platform"] == ["twitch"]


def test_twitch_callback_reports_redirect_mismatch(client):
    response = client.get(
        "/auth/twitch/callback?error=redirect_mismatch&error_description=redirect_uri_mismatch",
        follow_redirects=False,
    )

    parsed = urlparse(response.headers["location"])
    query = parse_qs(parsed.query)
    assert response.status_code == 307
    assert parsed.path.endswith("/login")
    assert query["auth_error"] == ["redirect_mismatch"]
    assert query["platform"] == ["twitch"]


def test_vk_callback_preserves_provider_access_denied(client):
    response = client.get(
        "/auth/vk/callback?error=access_denied&error_description=user_cancelled",
        follow_redirects=False,
    )

    parsed = urlparse(response.headers["location"])
    query = parse_qs(parsed.query)
    assert response.status_code == 307
    assert parsed.path.endswith("/login")
    assert query["auth_error"] == ["access_denied"]
    assert query["platform"] == ["vk"]


def test_twitch_callback_redirects_when_oauth_handler_fails(client, monkeypatch):
    import auth.twitch_auth as twitch_auth

    monkeypatch.setattr(twitch_auth, "TWITCH_CLIENT_ID", "test-client")
    monkeypatch.setattr(twitch_auth, "TWITCH_CLIENT_SECRET", "test-secret")
    monkeypatch.setattr(twitch_auth, "TWITCH_REDIRECT_URI", "http://localhost/auth/twitch/callback")

    class OkClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, **kwargs):
            if "oauth2/token" in url:
                return httpx.Response(
                    200,
                    json={
                        "access_token": "access",
                        "refresh_token": "refresh",
                        "expires_in": 3600,
                        "scope": ["user:read:email"],
                    },
                    request=httpx.Request(method, url),
                )
            return httpx.Response(
                200,
                json={"data": [{"id": "75969278", "login": "yourchy", "profile_image_url": "https://example.com/a.png"}]},
                request=httpx.Request(method, url),
            )

    async def failing_handler(**kwargs):
        raise HTTPException(status_code=500, detail="boom")

    monkeypatch.setattr(twitch_auth.httpx, "AsyncClient", lambda *args, **kwargs: OkClient())
    monkeypatch.setattr(twitch_auth.oauth_handler, "handle_oauth_callback", failing_handler)

    client.cookies.set("oauth_state", "release-state")
    response = client.get(
        "/auth/twitch/callback?code=test-code&state=release-state",
        follow_redirects=False,
    )

    parsed = urlparse(response.headers["location"])
    query = parse_qs(parsed.query)
    assert response.status_code == 307
    assert parsed.path.endswith("/login")
    assert query["auth_error"] == ["internal_error"]
    assert query["platform"] == ["twitch"]


def test_vk_login_reports_not_configured_without_internal_server_error(client, monkeypatch):
    import auth.vk_auth as vk_auth

    monkeypatch.setattr(vk_auth, "VK_CLIENT_ID", "")
    monkeypatch.setattr(vk_auth, "VK_REDIRECT_URI", "http://localhost/auth/vk/callback")

    response = client.get("/auth/vk/login", follow_redirects=False)

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "integration_not_configured",
        "platform": "vk",
        "message": "VK Live OAuth is not configured",
    }


def test_vk_callback_accepts_user_info_without_request_level_verify(client, monkeypatch):
    import auth.vk_auth as vk_auth

    monkeypatch.setattr(vk_auth, "VK_CLIENT_ID", "vk-client")
    monkeypatch.setattr(vk_auth, "VK_CLIENT_SECRET", "vk-secret")
    monkeypatch.setattr(vk_auth, "VK_REDIRECT_URI", "http://localhost/auth/vk/callback")

    class VkClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, **kwargs):
            assert "verify" not in kwargs
            if "oauth/server/token" in url:
                return httpx.Response(
                    200,
                    json={
                        "access_token": "vk-access",
                        "refresh_token": "vk-refresh",
                        "expires_in": 3600,
                        "scope": "",
                    },
                    request=httpx.Request(method, url),
                )
            return httpx.Response(
                200,
                json={
                    "data": {
                        "user": {
                            "id": 20416992,
                            "nick": "Zavtra_Zavod",
                            "avatar_url": "https://example.com/vk.png",
                        },
                        "channel": {"url": "https://live.vkvideo.ru/yourchy"},
                    }
                },
                request=httpx.Request(method, url),
            )

    async def successful_handler(**kwargs):
        assert kwargs["platform"] == Platform.VK
        assert kwargs["user_data"].platform_user_id == "20416992"
        assert kwargs["user_data"].username == "Zavtra_Zavod"
        assert kwargs["user_data"].channel_name == "yourchy"
        return SimpleNamespace(user=SimpleNamespace(id=9), session_id=None, redirect_url="http://localhost/dashboard")

    monkeypatch.setattr(vk_auth.httpx, "AsyncClient", lambda *args, **kwargs: VkClient())
    monkeypatch.setattr(vk_auth.oauth_handler, "handle_oauth_callback", successful_handler)
    monkeypatch.setattr(
        vk_auth.oauth_handler,
        "create_oauth_response",
        lambda result: vk_auth.RedirectResponse(url=result.redirect_url),
    )

    client.cookies.set("oauth_state_vk", "release-state")
    response = client.get(
        "/auth/vk/callback?code=test-code&state=release-state",
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"] == "http://localhost/dashboard"


@pytest.mark.asyncio
async def test_twitch_bot_validator_rejects_user_token_without_chat_scopes(monkeypatch):
    from services import bot_token_validator as validator_module

    async def get_user_token():
        return {"access_token": "user-token", "bot_login": "yourchy"}

    class ValidateClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, **kwargs):
            return httpx.Response(
                200,
                json={
                    "user_id": "75969278",
                    "login": "yourchy",
                    "expires_in": 3600,
                    "scopes": [
                        "user:read:email",
                        "channel:manage:broadcast",
                        "channel:manage:redemptions",
                    ],
                },
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(
        validator_module.twitch_bot_oauth_service,
        "get_bot_token",
        get_user_token,
    )
    monkeypatch.setattr(validator_module.httpx, "AsyncClient", lambda *args, **kwargs: ValidateClient())

    result = await bot_token_validator.validate_twitch_bot_token()

    assert result["valid"] is False
    assert result["error"] == "Twitch bot token is missing required chat scopes"
    assert result["missing_scopes"] == ["chat:edit", "chat:read"]


@pytest.mark.asyncio
async def test_twitch_bot_validator_retries_transient_network_errors(monkeypatch):
    from services import bot_token_validator as validator_module

    async def get_bot_token():
        return {"access_token": "bot-token", "bot_login": "paidviewer_bot"}

    async def noop_sleep(_delay):
        return None

    class FlakyValidateClient:
        attempts = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, **kwargs):
            FlakyValidateClient.attempts += 1
            if FlakyValidateClient.attempts < 3:
                raise httpx.ConnectError("dns failure", request=httpx.Request("GET", url))
            return httpx.Response(
                200,
                json={
                    "user_id": "bot-user",
                    "login": "paidviewer_bot",
                    "expires_in": 3600,
                    "scopes": ["chat:read", "chat:edit"],
                },
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(validator_module.twitch_bot_oauth_service, "get_bot_token", get_bot_token)
    monkeypatch.setattr(validator_module.asyncio, "sleep", noop_sleep)
    monkeypatch.setattr(validator_module.httpx, "AsyncClient", lambda *args, **kwargs: FlakyValidateClient())

    result = await bot_token_validator.validate_twitch_bot_token()

    assert result["valid"] is True
    assert FlakyValidateClient.attempts == 3


@pytest.mark.asyncio
async def test_twitch_bot_validator_marks_exhausted_network_error_transient(monkeypatch):
    from services import bot_token_validator as validator_module

    async def get_bot_token():
        return {"access_token": "bot-token", "bot_login": "paidviewer_bot"}

    async def noop_sleep(_delay):
        return None

    class BrokenValidateClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, **kwargs):
            raise httpx.ConnectError("dns failure", request=httpx.Request("GET", url))

    monkeypatch.setattr(validator_module.twitch_bot_oauth_service, "get_bot_token", get_bot_token)
    monkeypatch.setattr(validator_module.asyncio, "sleep", noop_sleep)
    monkeypatch.setattr(validator_module.httpx, "AsyncClient", lambda *args, **kwargs: BrokenValidateClient())

    result = await bot_token_validator.validate_twitch_bot_token()

    assert result["valid"] is False
    assert result["transient"] is True
    assert result["error"] == "Twitch token validation temporarily unavailable"


def test_logout_preserves_platform_tokens(authenticated_client, db_session, test_user):
    db_session.add(
        UserToken(
            user_id=test_user.id,
            platform="twitch",
            platform_user_id="logout-preserve",
            access_token="token",
            refresh_token="refresh",
            auth_type="full",
            is_active=True,
        )
    )
    db_session.commit()

    response = authenticated_client.post("/api/auth/logout")

    assert response.status_code == 200
    assert response.json()["tokens_deleted"] is False
    remaining = db_session.query(UserToken).filter(
        UserToken.user_id == test_user.id,
        UserToken.platform == "twitch",
        UserToken.platform_user_id == "logout-preserve",
    ).first()
    assert remaining is not None


@pytest.mark.asyncio
async def test_oauth_handler_merges_conflicting_twitch_identity_into_current_user(db_session):
    source_user = User(role="user", twitch_username="yourchy")
    target_user = User(role="user", vk_username="Zavtra_Zavod", vk_channel_name="yourchy")
    db_session.add_all([source_user, target_user])
    db_session.commit()
    db_session.refresh(source_user)
    db_session.refresh(target_user)

    db_session.add(
        UserToken(
            user_id=source_user.id,
            platform="twitch",
            platform_user_id="75969278",
            avatar_url="https://example.com/source.png",
            access_token="legacy-token",
            refresh_token="legacy-refresh",
            auth_type="full",
            is_active=True,
        )
    )
    db_session.commit()

    request = SimpleNamespace(
        cookies={},
        headers={"user-agent": "pytest"},
        client=SimpleNamespace(host="127.0.0.1"),
    )
    oauth_user_data = OAuthUserData(
        platform_user_id="75969278",
        avatar_url="https://example.com/new.png",
        access_token="fresh-token",
        refresh_token="fresh-refresh",
        expires_at=None,
        scopes=["channel:manage:broadcast"],
        username="yourchy",
    )

    result = await oauth_handler.handle_oauth_callback(
        request=request,
        db=db_session,
        platform=Platform.TWITCH,
        user_data=oauth_user_data,
        current_user={"id": target_user.id},
        auto_connect_bot=False,
    )

    db_session.expire_all()
    merged_user = db_session.query(User).filter(User.id == target_user.id).first()
    merged_token = db_session.query(UserToken).filter(
        UserToken.user_id == target_user.id,
        UserToken.platform == "twitch",
    ).all()

    assert result.user.id == target_user.id
    assert result.redirect_url.endswith("/dashboard/settings?auth_link=twitch&success=1")
    assert merged_user is not None
    assert merged_user.twitch_username == "yourchy"
    assert merged_user.vk_channel_name == "yourchy"
    assert db_session.query(User).filter(User.id == source_user.id).first() is None
    assert len(merged_token) == 1
    assert merged_token[0].platform_user_id == "75969278"


@pytest.mark.asyncio
async def test_oauth_handler_promotes_configured_admin_identity(db_session, monkeypatch):
    monkeypatch.setattr(
        "auth.oauth_handler.settings.admin_users",
        "twitch:75969278,vk:20416992",
        raising=False,
    )
    user = User(role="user")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    request = SimpleNamespace(
        cookies={},
        headers={"user-agent": "pytest"},
        client=SimpleNamespace(host="127.0.0.1"),
    )
    oauth_user_data = OAuthUserData(
        platform_user_id="75969278",
        avatar_url="https://example.com/admin.png",
        access_token="fresh-token",
        refresh_token="fresh-refresh",
        expires_at=None,
        scopes=["channel:manage:broadcast"],
        username="yourchy",
    )

    result = await oauth_handler.handle_oauth_callback(
        request=request,
        db=db_session,
        platform=Platform.TWITCH,
        user_data=oauth_user_data,
        current_user={"id": user.id},
        auto_connect_bot=False,
    )

    db_session.expire_all()
    admin_user = db_session.query(User).filter(User.id == result.user.id).one()

    assert admin_user.role == "admin"
    assert admin_user.is_admin is True


def test_stream_info_service_normalizes_vk_category_without_real_id(db_session):
    service = StreamInfoService(db_session)
    payload = {
        "title": "Stream offline",
        "category": "Just Chatting",
        "viewer_count": 0,
    }

    service._apply_category_contract("vk", payload)

    assert payload["category_id"] is None
    assert payload["category_name"] == "Just Chatting"
    assert payload["category"] == {
        "name": "Just Chatting",
        "title": "Just Chatting",
    }


def test_memealerts_streamer_id_prefers_id_claim():
    from api.memealerts_api import _extract_memealerts_streamer_id

    assert _extract_memealerts_streamer_id({"id": "streamer-id", "tid": "token-record-id"}) == "streamer-id"


def test_memealerts_streamer_id_uses_trusted_fallback_when_id_missing():
    from api.memealerts_api import _extract_memealerts_streamer_id

    assert _extract_memealerts_streamer_id({"tid": "token-record-id"}, "trusted-streamer-id") == "trusted-streamer-id"
