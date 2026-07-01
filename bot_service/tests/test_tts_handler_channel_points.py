from types import SimpleNamespace

import pytest

from services.tts_handler_service import TTSHandlerService


def test_channel_points_mode_requires_configured_reward_when_reward_missing():
    service = TTSHandlerService()
    settings = SimpleNamespace(tts_reward_ids={})

    assert service._validate_channel_points_mode(settings, "twitch", reward_id=None) == "reward_not_configured"


def test_channel_points_mode_still_requires_matching_reward_when_configured():
    service = TTSHandlerService()
    settings = SimpleNamespace(tts_reward_ids={"twitch": "reward-123"})

    assert service._validate_channel_points_mode(settings, "twitch", reward_id=None) == "wrong_reward"
    assert service._validate_channel_points_mode(settings, "twitch", reward_id="reward-999") == "wrong_reward"
    assert service._validate_channel_points_mode(settings, "twitch", reward_id="reward-123") is None


@pytest.mark.asyncio
async def test_forbidden_phrase_matches_inside_message():
    service = TTSHandlerService()
    async def get_filtered_words(_user_id):
        return [
            {"word": "123", "platform": "all"},
            {"word": "капс", "platform": "twitch"},
        ]

    tts_service = SimpleNamespace(get_filtered_words=get_filtered_words)

    assert await service._match_filtered_word(tts_service, 1, "twitch", "test 123") == "123"
    assert await service._match_filtered_word(tts_service, 1, "twitch", "test123") == "123"
    assert await service._match_filtered_word(tts_service, 1, "Twitch", "КАПС") == "капс"


@pytest.mark.asyncio
async def test_wait_for_tts_sink_handles_player_registration_race(monkeypatch):
    service = TTSHandlerService()
    calls = {"count": 0}

    def check_sink(*_args, **_kwargs):
        calls["count"] += 1
        return {"success": False, "error": "No active TTS player sink"} if calls["count"] == 1 else None

    monkeypatch.setattr(service, "_check_active_tts_sink", check_sink)

    result = await service._wait_for_active_tts_sink(
        {"user_id": 1},
        connection_manager=None,
        platform="twitch",
        timeout_sec=0.1,
        interval_sec=0.01,
    )

    assert result is None
    assert calls["count"] == 2


def test_memealerts_streamer_id_prefers_jwt_id_for_bonus_payload():
    from services.memealerts_service import MemeAlertsService

    assert (
        MemeAlertsService._resolve_streamer_id(
            {"id": "streamer-id", "tid": "token-record-id"},
            "old-local-token-id",
        )
        == "streamer-id"
    )


def test_memealerts_api_headers_are_server_to_server_safe():
    from services.memealerts_service import MEMEALERTS_BROWSER_HEADERS

    assert "Origin" not in MEMEALERTS_BROWSER_HEADERS
    assert "Referer" not in MEMEALERTS_BROWSER_HEADERS
    assert MEMEALERTS_BROWSER_HEADERS["Accept"] == "application/json"
