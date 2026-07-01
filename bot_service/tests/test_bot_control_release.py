from core.database import UserToken
from models.bot_token import BotToken


def test_chat_status_reports_missing_bot_oauth(authenticated_client, db, test_user):
    db.add(
        UserToken(
            user_id=test_user.id,
            platform="twitch",
            platform_user_id="twitch-user",
            access_token="user-access-token",
            refresh_token="user-refresh-token",
            is_active=True,
        )
    )
    db.commit()

    response = authenticated_client.get("/api/chat/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["connected"] is False
    assert payload["twitch"]["user_integration"] is True
    assert payload["twitch"]["bot_oauth"]["configured"] is False
    assert payload["twitch"]["reason"] == "bot_oauth_missing"


def test_chat_connect_does_not_report_success_without_bot_oauth(authenticated_client, db, test_user):
    db.add(
        UserToken(
            user_id=test_user.id,
            platform="twitch",
            platform_user_id="twitch-user",
            access_token="user-access-token",
            refresh_token="user-refresh-token",
            is_active=True,
        )
    )
    db.commit()

    response = authenticated_client.post("/api/chat/connect")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["code"] == "bot_oauth_missing"
    assert payload["status"]["connected"] is False


def test_chat_status_connected_requires_runtime_and_active_channel(
    authenticated_client,
    db,
    test_user,
    monkeypatch,
):
    db.add(
        UserToken(
            user_id=test_user.id,
            platform="twitch",
            platform_user_id="twitch-user",
            access_token="user-access-token",
            refresh_token="user-refresh-token",
            is_active=True,
        )
    )
    db.add(
        BotToken(
            platform="twitch",
            access_token="bot-access-token",
            refresh_token="bot-refresh-token",
            bot_login="paidviewer_bot",
            is_active=True,
        )
    )
    db.commit()

    class FakeRegistry:
        def is_twitch_running(self):
            return True

        def is_vk_running(self):
            return False

    class FakeConnectionManager:
        def is_channel_active(self, channel_name):
            return channel_name == test_user.twitch_username

    monkeypatch.setattr(
        "services.bot_control_service.get_bot_registry",
        lambda: FakeRegistry(),
    )
    monkeypatch.setattr(
        "services.bot_control_service.get_connection_manager",
        lambda: FakeConnectionManager(),
    )

    response = authenticated_client.get("/api/chat/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["connected"] is True
    assert payload["ready"] is True
    assert payload["platform"] == "twitch"
    assert payload["twitch"]["ready"] is True
