from urllib.parse import parse_qs, urlparse


def _redirect_uri(location: str) -> str:
    return parse_qs(urlparse(location).query)["redirect_uri"][0]


def test_twitch_login_uses_configured_redirect_uri(client, monkeypatch):
    import auth.twitch_auth as twitch_auth

    expected = "http://localhost/auth/twitch/callback"
    monkeypatch.setattr(twitch_auth, "TWITCH_CLIENT_ID", "test_client_id")
    monkeypatch.setattr(twitch_auth, "TWITCH_REDIRECT_URI", expected)

    response = client.get("/auth/twitch/login", follow_redirects=False)

    assert response.status_code == 307
    assert _redirect_uri(response.headers["location"]) == expected
    assert "oauth_state=" in response.headers.get("set-cookie", "")


def test_legacy_twitch_login_alias_uses_configured_redirect_uri(client, monkeypatch):
    import auth.twitch_auth as twitch_auth

    expected = "http://localhost:8000/auth/twitch/callback"
    monkeypatch.setattr(twitch_auth, "TWITCH_CLIENT_ID", "test_client_id")
    monkeypatch.setattr(twitch_auth, "TWITCH_REDIRECT_URI", expected)

    response = client.get("/api/auth/twitch/login", follow_redirects=False)

    assert response.status_code == 307
    assert _redirect_uri(response.headers["location"]) == expected
    assert "oauth_state=" in response.headers.get("set-cookie", "")


def test_twitch_login_reports_not_configured(client, monkeypatch):
    import auth.twitch_auth as twitch_auth

    monkeypatch.setattr(twitch_auth, "TWITCH_CLIENT_ID", "")
    monkeypatch.setattr(twitch_auth, "TWITCH_REDIRECT_URI", "http://localhost/auth/twitch/callback")

    response = client.get("/auth/twitch/login", follow_redirects=False)

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "integration_not_configured",
        "platform": "twitch",
        "message": "Twitch OAuth is not configured",
    }


def test_vk_login_uses_configured_redirect_uri(client, monkeypatch):
    import auth.vk_auth as vk_auth

    expected = "http://localhost/auth/vk/callback"
    monkeypatch.setattr(vk_auth, "VK_CLIENT_ID", "test_client_id")
    monkeypatch.setattr(vk_auth, "VK_REDIRECT_URI", expected)

    response = client.get("/auth/vk/login", follow_redirects=False)

    assert response.status_code == 307
    assert _redirect_uri(response.headers["location"]) == expected
    assert "oauth_state_vk=" in response.headers.get("set-cookie", "")


def test_legacy_vk_login_alias_uses_configured_redirect_uri(client, monkeypatch):
    import auth.vk_auth as vk_auth

    expected = "http://localhost:8000/auth/vk/callback"
    monkeypatch.setattr(vk_auth, "VK_CLIENT_ID", "test_client_id")
    monkeypatch.setattr(vk_auth, "VK_REDIRECT_URI", expected)

    response = client.get("/api/auth/vk/login", follow_redirects=False)

    assert response.status_code == 307
    assert _redirect_uri(response.headers["location"]) == expected
    assert "oauth_state_vk=" in response.headers.get("set-cookie", "")


def test_donationalerts_login_uses_configured_redirect_uri(authenticated_client, monkeypatch):
    import auth.donationalerts_auth as donationalerts_auth

    expected = "http://localhost/auth/donationalerts/callback"
    monkeypatch.setattr(donationalerts_auth.settings, "donationalerts_client_id", "test_client_id")
    monkeypatch.setattr(donationalerts_auth.settings, "donationalerts_redirect_uri", expected)

    response = authenticated_client.get("/auth/donationalerts/login", follow_redirects=False)

    assert response.status_code == 307
    assert _redirect_uri(response.headers["location"]) == expected
    assert "oauth_state_da=" in response.headers.get("set-cookie", "")


def test_twitch_bot_oauth_uses_configured_redirect_uri(monkeypatch):
    from services.twitch_bot_oauth_service import TwitchBotOAuthService
    from core.config import settings

    expected = "http://localhost/auth/twitch/bot/callback"
    monkeypatch.setattr(settings, "twitch_client_id", "test_client_id")
    monkeypatch.setattr(settings, "twitch_bot_redirect_uri", expected)

    auth_url = TwitchBotOAuthService.get_authorization_url("test-state")

    assert _redirect_uri(auth_url) == expected


def test_vk_bot_oauth_uses_configured_redirect_uri(monkeypatch):
    from services.vk_bot_oauth_service import VkBotOAuthService
    from core.config import settings

    expected = "http://localhost/auth/vk/bot/callback"
    monkeypatch.setattr(settings, "vk_client_id", "test_client_id")
    monkeypatch.setattr(settings, "vk_bot_redirect_uri", expected)

    auth_url = VkBotOAuthService.get_authorization_url("test-state")

    assert _redirect_uri(auth_url) == expected
