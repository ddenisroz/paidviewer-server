#!/usr/bin/env python3
"""Seed and refresh the catalog of global bot commands."""

from __future__ import annotations

import logging
import os
import sys
from typing import Iterable

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.database import BotCommand, get_db
from core.datetime_utils import utcnow_naive

logger = logging.getLogger(__name__)


GLOBAL_COMMAND_CATALOG: tuple[dict[str, object], ...] = (
    {
        "command_name": "help",
        "description": "Показать список всех доступных команд",
        "tags": "Общее",
        "allowed_roles": "all",
        "cooldown_seconds": 5,
    },
    {
        "command_name": "sr",
        "description": "Заказать YouTube видео (song request)",
        "tags": "Медиа и интерактивность",
        "allowed_roles": "all",
        "cooldown_seconds": 10,
    },
    {
        "command_name": "skip",
        "description": "Пропустить текущее видео",
        "tags": "Медиа и интерактивность",
        "allowed_roles": "moderator,broadcaster",
        "cooldown_seconds": 5,
    },
    {
        "command_name": "clear",
        "description": "Очистить очередь видео",
        "tags": "Медиа и интерактивность",
        "allowed_roles": "moderator,broadcaster",
        "cooldown_seconds": 10,
    },
    {
        "command_name": "queue",
        "description": "Показать очередь YouTube видео",
        "tags": "Медиа и интерактивность",
        "allowed_roles": "all",
        "cooldown_seconds": 10,
    },
    {
        "command_name": "wronglink",
        "description": "Отменить последнее заказанное вами видео",
        "tags": "Медиа и интерактивность",
        "allowed_roles": "all",
        "cooldown_seconds": 5,
    },
    {
        "command_name": "title",
        "description": "Сменить название стрима",
        "tags": "Управление трансляцией",
        "allowed_roles": "broadcaster",
        "cooldown_seconds": 30,
    },
    {
        "command_name": "game",
        "description": "Сменить категорию или игру стрима",
        "tags": "Управление трансляцией",
        "allowed_roles": "broadcaster",
        "cooldown_seconds": 30,
    },
    {
        "command_name": "ttsvolume",
        "description": "Настроить громкость TTS (0-100)",
        "tags": "TTS ИИ озвучка",
        "allowed_roles": "broadcaster,moderator",
        "cooldown_seconds": 5,
    },
    {
        "command_name": "ytvolume",
        "description": "Настроить громкость YouTube (0-100)",
        "tags": "Медиа и интерактивность",
        "allowed_roles": "broadcaster,moderator",
        "cooldown_seconds": 5,
    },
    {
        "command_name": "voice",
        "description": "Выбрать голос для TTS",
        "tags": "TTS ИИ озвучка",
        "allowed_roles": "all",
        "cooldown_seconds": 30,
    },
    {
        "command_name": "randomvoice",
        "description": "Выбрать случайный голос для TTS",
        "tags": "TTS ИИ озвучка",
        "allowed_roles": "all",
        "cooldown_seconds": 30,
    },
    {
        "command_name": "mute",
        "description": "Отключить TTS для пользователя",
        "tags": "TTS ИИ озвучка",
        "allowed_roles": "broadcaster,moderator",
        "cooldown_seconds": 5,
    },
    {
        "command_name": "unmute",
        "description": "Включить TTS для пользователя",
        "tags": "TTS ИИ озвучка",
        "allowed_roles": "broadcaster,moderator",
        "cooldown_seconds": 5,
    },
    {
        "command_name": "analyze",
        "description": "Отправить историю сообщений на анализ ИИ",
        "tags": "Анализ чата",
        "allowed_roles": "broadcaster",
        "cooldown_seconds": 60,
    },
    {
        "command_name": "givema",
        "alias": "memegrant",
        "description": "Выдать мемкоины (MemeAlerts) через чат",
        "tags": "MemeAlerts",
        "allowed_roles": "broadcaster,moderator",
        "cooldown_seconds": 5,
    },
)


def _iter_catalog() -> Iterable[dict[str, object]]:
    return GLOBAL_COMMAND_CATALOG


def sync_global_commands(db) -> tuple[int, int]:
    """Upsert the full global command catalog into the database."""

    commands_created = 0
    commands_updated = 0

    for cmd_data in _iter_catalog():
        existing = (
            db.query(BotCommand)
            .filter(
                BotCommand.user_id.is_(None),
                BotCommand.command_type == "global",
                BotCommand.command_name == cmd_data["command_name"],
            )
            .first()
        )

        if existing:
            existing.description = str(cmd_data["description"])
            existing.tags = str(cmd_data["tags"])
            existing.allowed_roles = str(cmd_data["allowed_roles"])
            existing.cooldown_seconds = int(cmd_data["cooldown_seconds"])
            existing.alias = str(cmd_data.get("alias") or "") or None
            existing.response_text = ""
            existing.platforms = "twitch,vk"
            existing.is_enabled = True
            existing.updated_at = utcnow_naive()
            commands_updated += 1
            continue

        db.add(
            BotCommand(
                user_id=None,
                channel_name=None,
                command_name=str(cmd_data["command_name"]),
                command_type="global",
                alias=str(cmd_data.get("alias") or "") or None,
                description=str(cmd_data["description"]),
                response_text="",
                is_enabled=True,
                platforms="twitch,vk",
                allowed_roles=str(cmd_data["allowed_roles"]),
                cooldown_seconds=int(cmd_data["cooldown_seconds"]),
                tags=str(cmd_data["tags"]),
                created_at=utcnow_naive(),
                updated_at=utcnow_naive(),
            )
        )
        commands_created += 1

    legacy_memegrant = (
        db.query(BotCommand)
        .filter(
            BotCommand.user_id.is_(None),
            BotCommand.command_type == "global",
            BotCommand.command_name == "memegrant",
        )
        .first()
    )
    if legacy_memegrant:
        legacy_memegrant.is_enabled = False
        legacy_memegrant.alias = None
        legacy_memegrant.updated_at = utcnow_naive()
        commands_updated += 1

    db.commit()
    return commands_created, commands_updated


def init_global_commands() -> tuple[int, int]:
    """Refresh the global commands using a managed database session."""

    db = next(get_db())
    try:
        created, updated = sync_global_commands(db)
        logger.info(
            "Global commands synced: created=%s updated=%s total=%s",
            created,
            updated,
            created + updated,
        )
        return created, updated
    except Exception:
        db.rollback()
        logger.exception("Failed to sync global commands")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    created_count, updated_count = init_global_commands()
    print("=" * 60)
    print("[WEB] ИНИЦИАЛИЗАЦИЯ ГЛОБАЛЬНЫХ КОМАНД")
    print("=" * 60)
    print(f"Создано: {created_count}")
    print(f"Обновлено: {updated_count}")
    print(f"Всего синхронизировано: {created_count + updated_count}")
    print("=" * 60)
