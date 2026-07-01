from core.database import BotCommand
from init_global_commands import sync_global_commands


def test_sync_global_commands_creates_stream_control_entries(db):
    created, updated = sync_global_commands(db)

    title_cmd = (
        db.query(BotCommand)
        .filter(BotCommand.command_type == "global", BotCommand.command_name == "title", BotCommand.user_id.is_(None))
        .one()
    )
    game_cmd = (
        db.query(BotCommand)
        .filter(BotCommand.command_type == "global", BotCommand.command_name == "game", BotCommand.user_id.is_(None))
        .one()
    )

    assert created > 0
    assert updated == 0
    assert title_cmd.tags == "Управление трансляцией"
    assert title_cmd.allowed_roles == "broadcaster"
    assert title_cmd.cooldown_seconds == 30
    assert title_cmd.platforms == "twitch,vk"
    assert game_cmd.tags == "Управление трансляцией"
    assert game_cmd.description == "Сменить категорию или игру стрима"


def test_sync_global_commands_refreshes_existing_metadata(db):
    legacy_title = BotCommand(
        user_id=None,
        channel_name=None,
        command_name="title",
        command_type="global",
        description="Legacy title",
        response_text="old",
        is_enabled=False,
        platforms="youtube",
        allowed_roles="all",
        cooldown_seconds=1,
        tags="Old",
    )
    db.add(legacy_title)
    db.commit()

    _created, updated = sync_global_commands(db)
    db.refresh(legacy_title)

    assert updated >= 1
    assert legacy_title.description == "Сменить название стрима"
    assert legacy_title.response_text == ""
    assert legacy_title.is_enabled is True
    assert legacy_title.platforms == "twitch,vk"
    assert legacy_title.allowed_roles == "broadcaster"
    assert legacy_title.cooldown_seconds == 30
    assert legacy_title.tags == "Управление трансляцией"
