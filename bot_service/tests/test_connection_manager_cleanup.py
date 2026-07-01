import asyncio
from contextlib import suppress

import pytest
from starlette.websockets import WebSocketState

from core.connection_manager import ConnectionManager


class _FakeWebSocket:
    def __init__(
        self,
        *,
        client_state: WebSocketState = WebSocketState.CONNECTED,
        application_state: WebSocketState = WebSocketState.CONNECTED,
    ):
        self.client_state = client_state
        self.application_state = application_state
        self.close_calls = 0

    async def close(self) -> None:
        self.close_calls += 1
        self.application_state = WebSocketState.DISCONNECTED


@pytest.mark.asyncio
async def test_cleanup_inactive_channels_removes_channel_scoped_runtime_state():
    manager = ConnectionManager()
    manager.active_sessions["Streamer_Channel"] = {"", None}
    manager.tts_enabled_channels.add("streamer_channel")
    manager.tts_enabled_twitch.add("streamer_channel")
    manager.tts_enabled_vk.add("streamer_channel")
    manager.basic_tts_enabled_channels.add("streamer_channel")
    manager.ai_tts_enabled_channels.add("streamer_channel")
    manager.blocked_bots.add("streamer_channel")
    manager.tts_volume_settings["streamer_channel"] = 0.75
    manager.voice_volume_settings["streamer_channel"] = {"main": 0.9}
    manager.youtube_settings["streamer_channel"] = {"playback_mode": "browser"}
    manager.youtube_queues["streamer_channel"] = ["video-1"]
    manager.current_videos["streamer_channel"] = {"video_id": "video-1"}
    manager.active_vk_bots["streamer_channel"] = {"status": "running"}

    removed = await manager.cleanup_inactive_channels()

    assert removed == 1
    assert "Streamer_Channel" not in manager.active_sessions
    assert "streamer_channel" not in manager.tts_enabled_channels
    assert "streamer_channel" not in manager.tts_enabled_twitch
    assert "streamer_channel" not in manager.tts_enabled_vk
    assert "streamer_channel" not in manager.basic_tts_enabled_channels
    assert "streamer_channel" not in manager.ai_tts_enabled_channels
    assert "streamer_channel" not in manager.blocked_bots
    assert "streamer_channel" not in manager.tts_volume_settings
    assert "streamer_channel" not in manager.voice_volume_settings
    assert "streamer_channel" not in manager.youtube_settings
    assert "streamer_channel" not in manager.youtube_queues
    assert "streamer_channel" not in manager.current_videos
    assert "streamer_channel" not in manager.active_vk_bots


@pytest.mark.asyncio
async def test_cleanup_inactive_clients_removes_disconnected_websockets():
    manager = ConnectionManager()
    manager.active_connections["connected"] = _FakeWebSocket()
    manager.active_connections["disconnected"] = _FakeWebSocket(
        application_state=WebSocketState.DISCONNECTED
    )
    manager.obs_connections["obs-disconnected"] = _FakeWebSocket(
        client_state=WebSocketState.DISCONNECTED
    )

    removed = await manager.cleanup_inactive_clients()

    assert removed == 2
    assert "connected" in manager.active_connections
    assert "disconnected" not in manager.active_connections
    assert "obs-disconnected" not in manager.obs_connections


@pytest.mark.asyncio
async def test_cleanup_cancels_pending_disconnects_and_clears_runtime_state():
    manager = ConnectionManager()
    websocket = _FakeWebSocket()
    manager.active_connections["user-1"] = websocket
    manager.obs_connections["obs-1"] = _FakeWebSocket()
    manager.youtube_obs_connections["yt-1"] = _FakeWebSocket()
    manager.audio_connections["audio-1"] = _FakeWebSocket()
    manager.active_sessions["streamer"] = {"session-1"}
    manager.tts_enabled_channels.add("streamer")
    manager.tts_enabled_twitch.add("streamer")
    manager.tts_enabled_vk.add("streamer")
    manager.basic_tts_enabled_channels.add("streamer")
    manager.ai_tts_enabled_channels.add("streamer")
    manager.blocked_bots.add("streamer")
    manager.youtube_queues["streamer"] = ["video-1"]
    manager.current_videos["streamer"] = {"video_id": "video-1"}
    manager.pending_verifications["token"] = {"user_id": 1}
    manager.verified_sessions.add("session-1")
    manager.active_vk_bots["streamer"] = {"status": "running"}
    manager.tts_volume_settings["streamer"] = 0.75
    manager.voice_volume_settings["streamer"] = {"main": 0.9}
    manager.youtube_settings["streamer"] = {"playback_mode": "browser"}
    manager.twitch_cache["stream-info"] = {"online": True}

    pending_task = asyncio.create_task(asyncio.sleep(60))
    manager.pending_tts_disconnects[42] = pending_task

    manager.cleanup()
    await asyncio.sleep(0)

    assert not manager.active_connections
    assert not manager.obs_connections
    assert not manager.youtube_obs_connections
    assert not manager.audio_connections
    assert not manager.active_sessions
    assert not manager.tts_enabled_channels
    assert not manager.tts_enabled_twitch
    assert not manager.tts_enabled_vk
    assert not manager.basic_tts_enabled_channels
    assert not manager.ai_tts_enabled_channels
    assert not manager.blocked_bots
    assert not manager.youtube_queues
    assert not manager.current_videos
    assert not manager.pending_verifications
    assert not manager.verified_sessions
    assert not manager.active_vk_bots
    assert not manager.tts_volume_settings
    assert not manager.voice_volume_settings
    assert not manager.youtube_settings
    assert not manager.twitch_cache
    assert not manager.pending_tts_disconnects
    assert websocket.close_calls == 1

    with suppress(asyncio.CancelledError):
        await pending_task
    assert pending_task.cancelled()
