from auth import vk_bot_oauth


def test_vk_bot_login_sets_lax_state_cookie(admin_client, monkeypatch):
    captured_state: dict[str, str] = {}

    def fake_get_authorization_url(state: str) -> str:
        captured_state["state"] = state
        return f"https://auth.live.vkvideo.ru/app/oauth2/authorize?state={state}"

    monkeypatch.setattr(
        vk_bot_oauth.vk_bot_oauth_service,
        "get_authorization_url",
        fake_get_authorization_url,
    )

    response = admin_client.get("/auth/vk/bot/login", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"].endswith(f"state={captured_state['state']}")

    set_cookie = response.headers["set-cookie"]
    assert f"vk_bot_oauth_state={captured_state['state']}" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie


def test_vk_bot_callback_preserves_provider_error_code(client):
    response = client.get(
        "/auth/vk/bot/callback?error=access_denied&error_description=user_cancelled",
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"].endswith("&platform=vk&bot_auth_error=access_denied")
    assert "vk_bot_oauth_state=" in response.headers.get("set-cookie", "")


def test_vk_bot_callback_redirects_invalid_state(client):
    client.cookies.set("vk_bot_oauth_state", "expected-state")

    response = client.get(
        "/auth/vk/bot/callback?code=test-code&state=wrong-state",
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"].endswith("&platform=vk&bot_auth_error=invalid_state")


def test_vk_bot_callback_reports_restart_failure(client, monkeypatch):
    async def fake_exchange_code_for_token(code: str):
        assert code == "vk-auth-code"
        return {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "expires_in": 3600,
            "scope": "chat:message:send",
        }

    async def fake_get_bot_user_info(access_token: str):
        assert access_token == "access-token"
        return {
            "id": "42",
            "login": "vk_paidviewer_bot",
        }

    async def fake_save_bot_token(**kwargs):
        assert kwargs["bot_user_id"] == "42"
        assert kwargs["bot_login"] == "vk_paidviewer_bot"
        return True

    class FakeRegistry:
        def is_vk_running(self) -> bool:
            return False

    class FakeConnectionManager:
        async def get_vk_channels_for_bot(self, db):
            return ["streamer_channel"]

    async def fake_initialize_vk_bot(channels):
        assert channels == ["streamer_channel"]
        return False

    monkeypatch.setattr(
        vk_bot_oauth.vk_bot_oauth_service,
        "exchange_code_for_token",
        fake_exchange_code_for_token,
    )
    monkeypatch.setattr(
        vk_bot_oauth.vk_bot_oauth_service,
        "get_bot_user_info",
        fake_get_bot_user_info,
    )
    monkeypatch.setattr(
        vk_bot_oauth.vk_bot_oauth_service,
        "save_bot_token",
        fake_save_bot_token,
    )
    monkeypatch.setattr(
        "core.connection_manager.get_connection_manager",
        lambda: FakeConnectionManager(),
    )
    monkeypatch.setattr(
        "startup.bot_registry.get_bot_registry",
        lambda: FakeRegistry(),
    )
    monkeypatch.setattr(
        "startup.bot_initializer.initialize_vk_bot",
        fake_initialize_vk_bot,
    )

    client.cookies.set("vk_bot_oauth_state", "expected-state")

    response = client.get(
        "/auth/vk/bot/callback?code=vk-auth-code&state=expected-state",
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"].endswith("&platform=vk&bot_auth_error=restart_failed")
