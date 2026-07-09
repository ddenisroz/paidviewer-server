import pytest

from core.config import settings
from services.twitch_bot_oauth_service import (
    TwitchBotOAuthService,
    UnexpectedTwitchBotAccountError,
    twitch_bot_oauth_service,
)


def test_twitch_bot_login_requires_admin(client):
    response = client.get("/auth/twitch/bot/login", follow_redirects=False)

    assert response.status_code == 403


def test_expected_twitch_bot_identity_is_case_insensitive(monkeypatch):
    monkeypatch.setattr(settings, "twitch_bot_expected_login", "pa1dviewer")
    monkeypatch.setattr(settings, "twitch_bot_expected_user_id", None)

    TwitchBotOAuthService.assert_expected_bot_identity("12345", "Pa1dViewer")


def test_expected_twitch_bot_identity_rejects_other_login(monkeypatch):
    monkeypatch.setattr(settings, "twitch_bot_expected_login", "pa1dviewer")
    monkeypatch.setattr(settings, "twitch_bot_expected_user_id", None)

    with pytest.raises(UnexpectedTwitchBotAccountError):
        TwitchBotOAuthService.assert_expected_bot_identity("999", "another_account")


def test_expected_twitch_bot_identity_checks_immutable_user_id(monkeypatch):
    monkeypatch.setattr(settings, "twitch_bot_expected_login", "pa1dviewer")
    monkeypatch.setattr(settings, "twitch_bot_expected_user_id", "12345")

    with pytest.raises(UnexpectedTwitchBotAccountError):
        TwitchBotOAuthService.assert_expected_bot_identity("999", "pa1dviewer")


def test_twitch_bot_callback_rejects_and_revokes_other_account(client, monkeypatch):
    revoked_tokens: list[str] = []
    saved_tokens: list[str] = []

    async def fake_exchange_code_for_token(code: str):
        assert code == "oauth-code"
        return {
            "access_token": "unexpected-access-token",
            "refresh_token": "unexpected-refresh-token",
            "expires_in": 3600,
            "scope": ["chat:read"],
        }

    async def fake_get_bot_user_info(access_token: str):
        assert access_token == "unexpected-access-token"
        return {"id": "999", "login": "another_account"}

    async def fake_revoke_access_token(access_token: str):
        revoked_tokens.append(access_token)

    async def fake_save_bot_token(**kwargs):
        saved_tokens.append(kwargs["access_token"])
        return True

    monkeypatch.setattr(settings, "twitch_bot_expected_login", "pa1dviewer")
    monkeypatch.setattr(settings, "twitch_bot_expected_user_id", None)
    monkeypatch.setattr(
        twitch_bot_oauth_service,
        "exchange_code_for_token",
        fake_exchange_code_for_token,
    )
    monkeypatch.setattr(
        twitch_bot_oauth_service,
        "get_bot_user_info",
        fake_get_bot_user_info,
    )
    monkeypatch.setattr(
        twitch_bot_oauth_service,
        "revoke_access_token",
        fake_revoke_access_token,
    )
    monkeypatch.setattr(
        twitch_bot_oauth_service,
        "save_bot_token",
        fake_save_bot_token,
    )

    client.cookies.set("bot_oauth_state", "expected-state")
    response = client.get(
        "/auth/twitch/bot/callback?code=oauth-code&state=expected-state",
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert "bot_auth_error=unexpected_account" in response.headers["location"]
    assert revoked_tokens == ["unexpected-access-token"]
    assert saved_tokens == []
    assert "bot_oauth_state=" in response.headers.get("set-cookie", "")
