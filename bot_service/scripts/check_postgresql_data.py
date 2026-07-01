#!/usr/bin/env python
"""Show a compact PostgreSQL data summary for the current backend."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

BOT_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(BOT_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(BOT_SERVICE_ROOT))

load_dotenv(BOT_SERVICE_ROOT / ".env")

from core.database import (  # noqa: E402
    BotCommand,
    ChannelReward,
    ChatMessage,
    DropsConfig,
    RewardQueue,
    User,
    UserSession,
    UserSettings,
    UserToken,
    WhitelistedChannel,
)


def _mask_database_url(database_url: str) -> str:
    if "@" not in database_url:
        return database_url
    return database_url.split("@", maxsplit=1)[1]


def main() -> int:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("[ERROR] DATABASE_URL is not set")
        return 1

    print("=" * 64)
    print("POSTGRESQL SUMMARY")
    print("=" * 64)
    print(f"Database: {_mask_database_url(database_url)}")
    print()

    try:
        engine = create_engine(database_url)
        Session = sessionmaker(bind=engine)
        session = Session()

        tables_to_check = [
            ("Users", User),
            ("User settings", UserSettings),
            ("User tokens", UserToken),
            ("User sessions", UserSession),
            ("Bot commands", BotCommand),
            ("Chat messages", ChatMessage),
            ("Drops config", DropsConfig),
            ("Whitelisted channels", WhitelistedChannel),
            ("Channel rewards", ChannelReward),
            ("Reward queue", RewardQueue),
        ]

        total_records = 0
        print("[TABLE STATISTICS]")
        print("-" * 64)
        for table_name, model in tables_to_check:
            count = session.query(model).count()
            total_records += count
            status = "[OK]" if count > 0 else "[EMPTY]"
            print(f"{status} {table_name:.<40} {count:>6}")
        print("-" * 64)
        print(f"Total rows: {total_records}")
        print()

        users = session.query(User).limit(5).all()
        if users:
            print("[USERS]")
            for user in users:
                platforms = []
                if user.twitch_username:
                    platforms.append(f"Twitch: {user.twitch_username}")
                if user.vk_username:
                    platforms.append(f"VK: {user.vk_username}")
                role = "admin" if user.role == "admin" else "user"
                platform_label = ", ".join(platforms) if platforms else "no platform"
                print(f"- id={user.id} role={role} {platform_label}")
            print()

        recent_messages = session.query(ChatMessage).order_by(ChatMessage.timestamp.desc()).limit(5).all()
        if recent_messages:
            print("[LATEST MESSAGES]")
            for message in recent_messages:
                print(f"- [{message.timestamp}] {message.author_username}: {message.message[:60]}")
            print()

        with engine.connect() as conn:
            version = conn.execute(text("SELECT version();")).scalar()
            version_label = str(version).split(",", maxsplit=1)[0]
            print(f"PostgreSQL: {version_label}")

        session.close()
        engine.dispose()
        print("\n[OK] Check completed")
        return 0
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
