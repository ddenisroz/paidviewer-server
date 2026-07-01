from unittest.mock import patch

from core.config import settings


def _csrf_headers(client) -> dict[str, str]:
    client.get("/api/auth/status")
    csrf_token = client.cookies.get("csrf_token")
    return {"X-CSRF-Token": csrf_token} if csrf_token else {}


def test_dev_login_sets_session_cookie_for_existing_user(client, test_user):
    original_environment = settings.environment
    settings.environment = "development"

    try:
        with patch("api.auth_api.session_manager.create_session", return_value="dev-session-123") as mock_create_session:
            response = client.post(
                "/api/auth/dev-login",
                json={"nickname": test_user.twitch_username},
                headers=_csrf_headers(client),
            )

        assert response.status_code == 200
        assert response.json()["authenticated"] is True
        assert response.json()["user"]["twitch_username"] == test_user.twitch_username
        assert response.cookies.get("session_id") == "dev-session-123"
        mock_create_session.assert_called_once()
    finally:
        settings.environment = original_environment


def test_dev_login_rejects_unknown_user(client):
    original_environment = settings.environment
    settings.environment = "development"

    try:
        response = client.post(
            "/api/auth/dev-login",
            json={"nickname": "missing-user"},
            headers=_csrf_headers(client),
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Пользователь с таким ником не найден"
    finally:
        settings.environment = original_environment


def test_dev_login_hidden_outside_development(client, test_user):
    original_environment = settings.environment
    settings.environment = "production"

    try:
        response = client.post(
            "/api/auth/dev-login",
            json={"nickname": test_user.twitch_username},
            headers=_csrf_headers(client),
        )

        assert response.status_code == 404
    finally:
        settings.environment = original_environment
