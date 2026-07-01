from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from core.database import BotCommand
from repositories.command_repository import CommandRepository
from services.command_cooldown_store import CommandCooldownStore
from services.command_service import CommandService


class _FakeRedis:
    def __init__(self) -> None:
        self.entries: dict[str, tuple[int, str]] = {}

    def exists(self, key: str) -> int:
        return 1 if key in self.entries else 0

    def setex(self, key: str, ttl: int, value: str) -> bool:
        self.entries[key] = (ttl, value)
        return True


def _command(**overrides):
    payload = {
        "id": 42,
        "cooldown_seconds": 30,
        "platforms": "twitch",
        "channel_name": "demo_channel",
        "user_id": 7,
        "command_name": "hello",
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def test_command_service_uses_redis_cooldown_store():
    fake_redis = _FakeRedis()
    service = CommandService(cooldown_store=CommandCooldownStore(redis_client=fake_redis))
    command = _command()

    assert service.check_cooldown(command, "viewer_1") is True

    service.update_cooldown(command, "viewer_1")

    assert service.check_cooldown(command, "viewer_1") is False

    cooldown_key = next(iter(fake_redis.entries))
    assert "platform:twitch" in cooldown_key
    assert "channel:demo_channel" in cooldown_key
    assert "command:42" in cooldown_key
    assert "viewer:viewer_1" in cooldown_key


def test_command_cooldown_store_memory_fallback_expires_entries(monkeypatch):
    now = datetime(2026, 4, 5, 12, 0, 0)

    def _now():
        return now

    monkeypatch.setattr("services.command_cooldown_store.utcnow_naive", _now)

    store = CommandCooldownStore(redis_url="")
    service = CommandService(cooldown_store=store)
    command = _command(cooldown_seconds=10, platforms="vk", channel_name="vk_demo")

    service.update_cooldown(command, "viewer_2")

    assert service.check_cooldown(command, "viewer_2") is False

    now = now + timedelta(seconds=11)

    assert service.check_cooldown(command, "viewer_2") is True


def test_update_custom_command_renames_trigger(db, test_user):
    cmd = BotCommand(
        command_name="oldname",
        command_type="custom",
        user_id=test_user.id,
        response_text="Hello",
        is_enabled=True,
        platforms="all",
    )
    db.add(cmd)
    db.commit()

    CommandService().update_command(cmd.id, test_user.id, {"command_name": "!newname"}, db)

    db.refresh(cmd)
    assert cmd.command_name == "newname"


def test_create_global_override_alias_is_resolved(db, test_user):
    global_cmd = BotCommand(
        command_name="title",
        command_type="global",
        user_id=None,
        response_text="Set title",
        is_enabled=True,
        platforms="all",
    )
    db.add(global_cmd)
    db.commit()

    result = CommandService().create_command_override(
        user_id=test_user.id,
        command_name="title",
        alias="streamtitle",
        db=db,
    )

    assert result["data"]["alias"] == "streamtitle"
    found = CommandRepository(db).find_command("streamtitle", test_user.id, "twitch")
    assert found is not None
    assert found.command_name == "title"


def test_global_override_alias_cannot_shadow_global_command(db, test_user):
    db.add_all(
        [
            BotCommand(
                command_name="title",
                command_type="global",
                user_id=None,
                response_text="Set title",
                is_enabled=True,
                platforms="all",
            ),
            BotCommand(
                command_name="game",
                command_type="global",
                user_id=None,
                response_text="Set game",
                is_enabled=True,
                platforms="all",
            ),
        ]
    )
    db.commit()

    with pytest.raises(ValueError, match="already in use"):
        CommandService().create_command_override(
            user_id=test_user.id,
            command_name="title",
            alias="game",
            db=db,
        )
