from unittest.mock import AsyncMock

import pytest

from services.voice_management_service import VoiceManagementService


@pytest.mark.asyncio
async def test_update_user_voice_settings_creates_and_updates_global_override(db, test_user):
    service = VoiceManagementService(db)
    service.get_voice_info = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "id": 5,
            "name": "female_1",
            "type": "global",
            "is_global": True,
        }
    )

    created = await service.update_user_voice_settings(
        user_id=test_user.id,
        voice_id=5,
        settings_data={
            "cfg_strength": 2.5,
            "speed_preset": "fast",
            "volume": 70,
        },
        provider="f5",
    )

    assert created["voice_id"] == 5
    assert created["voice_name"] == "female_1"
    assert created["tts_provider"] == "f5"
    assert created["cfg_strength"] == 2.5
    assert created["speed_preset"] == "fast"
    assert created["volume"] == 70

    stored = service.repository.get_by_user_and_voice_id(
        test_user.id,
        5,
        tts_provider="f5",
    )
    assert stored is not None
    assert stored.speed_preset == "fast"

    updated = await service.update_user_voice_settings(
        user_id=test_user.id,
        voice_id=5,
        settings_data={
            "cfg_strength": 1.7,
            "speed_preset": "slow",
            "volume": 55,
        },
        provider="f5",
    )

    assert updated["id"] == created["id"]
    assert updated["cfg_strength"] == 1.7
    assert updated["speed_preset"] == "slow"
    assert updated["volume"] == 55
