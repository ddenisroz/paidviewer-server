from repositories.tts_settings_repository import TTSSettingsRepository
from services.youtube.reward_settings import (
    apply_youtube_settings_update,
    build_youtube_settings_response,
    get_platform_reward_configuration,
)


def _csrf_headers(client) -> dict[str, str]:
    token = client.cookies.get("csrf_token")
    return {"X-CSRF-Token": token} if token else {}


def test_apply_youtube_settings_update_migrates_legacy_payload_to_canonical_fields():
    current_settings = {
        "playback_mode": "browser",
        "requests_reward_twitch_enabled": True,
        "requests_reward_twitch_id": "tw_reward",
        "requests_reward_vk_enabled": False,
        "requests_reward_vk_id": "old_vk_reward",
    }

    updated = apply_youtube_settings_update(
        current_settings,
        {
            "requests_reward_enabled": True,
            "requests_reward_platform": "vk",
            "requests_reward_id": "vk_reward",
        },
    )

    assert "requests_reward_enabled" not in updated
    assert "requests_reward_id" not in updated
    assert "requests_reward_platform" not in updated
    assert updated["requests_reward_twitch_enabled"] is False
    assert updated["requests_reward_twitch_id"] == "tw_reward"
    assert updated["requests_reward_vk_enabled"] is True
    assert updated["requests_reward_vk_id"] == "vk_reward"


def test_build_youtube_settings_response_keeps_legacy_compat_fields():
    payload = build_youtube_settings_response(
        {
            "playback_mode": "obs",
            "volume_level": 65,
            "requests_command_enabled": False,
            "requests_reward_twitch_enabled": False,
            "requests_reward_twitch_id": None,
            "requests_reward_vk_enabled": True,
            "requests_reward_vk_id": "VK Reward",
        }
    )

    assert payload["playback_mode"] == "obs"
    assert payload["volume_level"] == 65
    assert payload["requests_command_enabled"] is False
    assert payload["requests_reward_enabled"] is True
    assert payload["requests_reward_platform"] == "vk"
    assert payload["requests_reward_id"] == "VK Reward"
    assert payload["requests_reward_twitch_enabled"] is False
    assert payload["requests_reward_vk_enabled"] is True


def test_get_platform_reward_configuration_reads_legacy_compat_values():
    reward_config = get_platform_reward_configuration(
        {
            "requests_reward_enabled": True,
            "requests_reward_platform": "vk",
            "requests_reward_id": "VK Video Reward",
        },
        platform="vk",
    )

    assert reward_config["enabled"] is True
    assert reward_config["reward_value"] == "VK Video Reward"


def test_youtube_settings_route_stores_canonical_reward_state(authenticated_client, db, test_user):
    response = authenticated_client.post(
        "/api/tts/youtube-settings",
        json={
            "playback_mode": "browser",
            "requests_reward_enabled": True,
            "requests_reward_platform": "vk",
            "requests_reward_id": "VK Video Reward",
        },
        headers=_csrf_headers(authenticated_client),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["requests_reward_enabled"] is True
    assert payload["requests_reward_platform"] == "vk"
    assert payload["requests_reward_id"] == "VK Video Reward"
    assert payload["requests_reward_vk_enabled"] is True
    assert payload["requests_reward_vk_id"] == "VK Video Reward"
    assert payload["requests_reward_twitch_enabled"] is False

    repo = TTSSettingsRepository(db)
    settings = repo.get_or_create(user_id=test_user.id)
    youtube_settings = settings.youtube_settings or {}

    assert "requests_reward_enabled" not in youtube_settings
    assert "requests_reward_id" not in youtube_settings
    assert "requests_reward_platform" not in youtube_settings
    assert youtube_settings["requests_reward_vk_enabled"] is True
    assert youtube_settings["requests_reward_vk_id"] == "VK Video Reward"


def test_youtube_settings_rejects_paid_orders_without_donationalerts(authenticated_client):
    response = authenticated_client.post(
        "/api/tts/youtube-settings",
        json={
            "paid_orders_enabled": True,
            "donationalerts_video_enabled": True,
        },
        headers=_csrf_headers(authenticated_client),
    )

    assert response.status_code == 400
    assert "DonationAlerts" in response.json()["detail"]
