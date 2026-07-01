# bot_service/tests/test_api_tts.py
"""
API tests for current TTS routes.
"""
from unittest.mock import patch

from api.tts import channel_points_routes
from models.tts import TTSBlockedUser
from repositories.tts_settings_repository import TTSSettingsRepository
from services.tts.tts_service import (
    BlockTargetNotFoundError,
    BlockTargetVerificationUnavailableError,
    TTSService,
)


def _csrf_headers(authenticated_client):
    # Any GET /api/* sets csrf_token cookie via middleware.
    warmup = authenticated_client.get("/api/tts/status")
    assert warmup.status_code == 200
    token = authenticated_client.cookies.get("csrf_token")
    assert token
    return {"X-CSRF-Token": token}


class _FakePlatformRewardsService:
    def __init__(self, rewards):
        self.rewards = rewards

    async def get_rewards(self, user_id, platform, db):
        return self.rewards


class TestTTSAPI:
    """Tests for TTS API endpoints."""

    def test_tts_status(self, authenticated_client):
        response = authenticated_client.get("/api/tts/status")
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert "engine_type" in data
        assert "advanced_provider" in data
        assert data.get("official_modes") == ["cloud", "self_host"]
        assert "provider_matrix" in data
        assert "active_contract" in data

    def test_tts_settings(self, authenticated_client):
        response = authenticated_client.get("/api/tts/settings")
        assert response.status_code == 200
        data = response.json()
        assert "engine" in data
        assert "advanced_provider" in data

    def test_update_tts_settings(self, authenticated_client):
        headers = _csrf_headers(authenticated_client)
        response = authenticated_client.post(
            "/api/tts/settings",
            json={"voice": "default_voice", "maxMessageLength": 150},
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True

    def test_attach_tts_reward_succeeds_for_existing_input_reward(
        self, authenticated_client, db, test_user, monkeypatch
    ):
        monkeypatch.setattr(
            channel_points_routes,
            "get_platform_rewards_service",
            lambda: _FakePlatformRewardsService(
                [
                    {
                        "id": "reward-1",
                        "title": "TTS message",
                        "cost": 500,
                        "is_user_input_required": True,
                    }
                ]
            ),
        )

        response = authenticated_client.post(
            "/api/tts/rewards/attach",
            json={"platform": "twitch", "reward_id": "reward-1"},
            headers=_csrf_headers(authenticated_client),
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert payload["platform"] == "twitch"
        assert payload["reward_id"] == "reward-1"
        assert payload["reward_title"] == "TTS message"

        settings = TTSSettingsRepository(db).get_or_create(user_id=test_user.id)
        assert settings.tts_reward_ids["twitch"] == "reward-1"

    def test_attach_tts_reward_returns_404_for_unknown_reward(
        self, authenticated_client, monkeypatch
    ):
        monkeypatch.setattr(
            channel_points_routes,
            "get_platform_rewards_service",
            lambda: _FakePlatformRewardsService(
                [
                    {
                        "id": "reward-1",
                        "title": "TTS message",
                        "cost": 500,
                        "is_user_input_required": True,
                    }
                ]
            ),
        )

        response = authenticated_client.post(
            "/api/tts/rewards/attach",
            json={"platform": "twitch", "reward_id": "missing"},
            headers=_csrf_headers(authenticated_client),
        )

        assert response.status_code == 404

    def test_attach_tts_reward_returns_400_without_user_input(
        self, authenticated_client, monkeypatch
    ):
        monkeypatch.setattr(
            channel_points_routes,
            "get_platform_rewards_service",
            lambda: _FakePlatformRewardsService(
                [
                    {
                        "id": "reward-1",
                        "title": "No input",
                        "cost": 500,
                        "is_user_input_required": False,
                    }
                ]
            ),
        )

        response = authenticated_client.post(
            "/api/tts/rewards/attach",
            json={"platform": "twitch", "reward_id": "reward-1"},
            headers=_csrf_headers(authenticated_client),
        )

        assert response.status_code == 400

    def test_delete_tts_reward_detaches_without_platform_delete(
        self, authenticated_client, db, test_user
    ):
        repo = TTSSettingsRepository(db)
        settings = repo.get_or_create(user_id=test_user.id)
        repo.update_settings(settings, {"tts_reward_ids": {"twitch": "reward-1", "vk": "vk-reward"}})

        with patch("platforms.registry.platform_registry.get") as get_platform:
            response = authenticated_client.delete(
                "/api/tts/rewards/twitch",
                headers=_csrf_headers(authenticated_client),
            )

        assert response.status_code == 200
        get_platform.assert_not_called()
        db.expire_all()
        settings = repo.get_or_create(user_id=test_user.id)
        assert settings.tts_reward_ids == {"vk": "vk-reward"}

    def test_tts_filtered_words(self, authenticated_client):
        response = authenticated_client.get("/api/tts/filtered-words")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert isinstance(data.get("data"), list)

    def test_add_and_remove_filtered_word(self, authenticated_client):
        headers = _csrf_headers(authenticated_client)

        add_response = authenticated_client.post(
            "/api/tts/filtered-words",
            json={"word": "test_word", "platform": "twitch"},
            headers=headers,
        )
        assert add_response.status_code in [200, 400]

        remove_response = authenticated_client.delete(
            "/api/tts/filtered-words/999999",
            headers=headers,
        )
        assert remove_response.status_code in [200, 404]

    def test_tts_synthesis_requires_text(self, authenticated_client):
        headers = _csrf_headers(authenticated_client)
        response = authenticated_client.post(
            "/api/tts/synthesize",
            json={"voice": "default_voice"},
            headers=headers,
        )
        assert response.status_code == 400

    def test_tts_health_check(self, authenticated_client):
        f5_response = authenticated_client.get("/api/tts/health", params={"provider": "f5"})
        gcloud_response = authenticated_client.get("/api/tts/health", params={"provider": "gcloud"})

        assert f5_response.status_code in [200, 500]
        assert gcloud_response.status_code in [200, 500]
        if f5_response.status_code == 200:
            payload = f5_response.json()
            assert "official_mode" in payload
            assert "slot_allowed" in payload
            assert "recommended_path" in payload

    def test_youtube_settings_endpoints_absent_or_legacy(self, authenticated_client):
        get_response = authenticated_client.get("/api/tts/youtube-settings")
        assert get_response.status_code in [200, 404]
        token = authenticated_client.cookies.get("csrf_token")
        headers = {"X-CSRF-Token": token} if token else _csrf_headers(authenticated_client)

        post_response = authenticated_client.post(
            "/api/tts/youtube-settings",
            json={"playback_mode": "browser", "volume_level": 80},
            headers=headers,
        )
        assert post_response.status_code in [200, 404]

    def test_block_user_returns_404_for_unknown_username(self, authenticated_client, monkeypatch):
        async def _raise_not_found(self, **_kwargs):
            raise BlockTargetNotFoundError("Twitch user 'ghost' does not exist")

        monkeypatch.setattr(TTSService, "ensure_block_target_exists", _raise_not_found)

        response = authenticated_client.post(
            "/api/tts/block",
            json={"username": "ghost", "platform": "twitch"},
            headers=_csrf_headers(authenticated_client),
        )

        assert response.status_code == 404
        assert "does not exist" in response.json()["detail"]

    def test_block_user_returns_503_when_verification_unavailable(self, authenticated_client, monkeypatch):
        async def _raise_unavailable(self, **_kwargs):
            raise BlockTargetVerificationUnavailableError("Failed to verify Twitch user right now. Try again later.")

        monkeypatch.setattr(TTSService, "ensure_block_target_exists", _raise_unavailable)

        response = authenticated_client.post(
            "/api/tts/block",
            json={"username": "ghost", "platform": "twitch"},
            headers=_csrf_headers(authenticated_client),
        )

        assert response.status_code == 503
        assert "Try again later" in response.json()["detail"]

    def test_delete_blocked_user_by_id(self, authenticated_client, db, test_user):
        blocked_user = TTSBlockedUser(
            user_id=test_user.id,
            channel_name=test_user.twitch_username,
            platform="twitch",
            username="annoying_viewer",
        )
        db.add(blocked_user)
        db.commit()
        db.refresh(blocked_user)

        response = authenticated_client.delete(
            f"/api/tts/blocked/{blocked_user.id}",
            headers=_csrf_headers(authenticated_client),
        )

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert db.query(TTSBlockedUser).filter(TTSBlockedUser.id == blocked_user.id).first() is None
