from types import SimpleNamespace

import pytest

from models.user import User
from platforms.twitch import TwitchPlatform


class _FakeChannel:
    def __init__(self, name: str):
        self.name = name
        self.sent_messages: list[str] = []

    async def send(self, message: str) -> None:
        self.sent_messages.append(message)


@pytest.mark.asyncio
async def test_twitch_send_chat_message_uses_connected_runtime_channel(db, monkeypatch):
    user = User(twitch_username="streamer_channel", role="user", is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)

    channel = _FakeChannel("streamer_channel")
    fake_bot = SimpleNamespace(connected_channels=[channel])
    fake_registry = SimpleNamespace(twitch_bot=fake_bot)

    monkeypatch.setattr("platforms.twitch.get_db", lambda: iter([db]))
    monkeypatch.setattr("startup.bot_registry.get_bot_registry", lambda: fake_registry)
    monkeypatch.setattr("platforms.twitch.TwitchOAuth.from_settings", lambda: SimpleNamespace())
    monkeypatch.setattr("platforms.twitch.TwitchClient", lambda oauth: SimpleNamespace())

    platform = TwitchPlatform()

    result = await platform.send_chat_message(user.id, "hello from test")

    assert result is True
    assert channel.sent_messages == ["hello from test"]


@pytest.mark.asyncio
async def test_twitch_send_chat_message_returns_false_when_runtime_channel_missing(db, monkeypatch):
    user = User(twitch_username="streamer_channel", role="user", is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)

    fake_bot = SimpleNamespace(connected_channels=[])
    fake_registry = SimpleNamespace(twitch_bot=fake_bot)

    monkeypatch.setattr("platforms.twitch.get_db", lambda: iter([db]))
    monkeypatch.setattr("startup.bot_registry.get_bot_registry", lambda: fake_registry)
    monkeypatch.setattr("platforms.twitch.TwitchOAuth.from_settings", lambda: SimpleNamespace())
    monkeypatch.setattr("platforms.twitch.TwitchClient", lambda oauth: SimpleNamespace())

    platform = TwitchPlatform()

    result = await platform.send_chat_message(user.id, "hello from test")

    assert result is False
