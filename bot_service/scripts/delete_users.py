#!/usr/bin/env python3
"""Safely delete selected users with a dry-run preview."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

BOT_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(BOT_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(BOT_SERVICE_ROOT))

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

if load_dotenv:
    load_dotenv(BOT_SERVICE_ROOT / ".env", override=False)

from models import SessionLocal  # noqa: E402
from repositories.user_repository import UserRepository  # noqa: E402
from services.user_cleanup_service import user_cleanup_service  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview and safely perform permanent deletion of selected PostgreSQL users.",
    )
    parser.add_argument("--list", action="store_true", help="Show current users and exit.")
    parser.add_argument("--user-id", type=int, action="append", default=[], help="User ID to delete.")
    parser.add_argument("--twitch", action="append", default=[], help="Twitch username to delete.")
    parser.add_argument("--vk", action="append", default=[], help="VK username to delete.")
    parser.add_argument("--yes", action="store_true", help="Perform deletion after the preview.")
    return parser.parse_args()


def list_users() -> int:
    db = SessionLocal()
    try:
        repo = UserRepository(db)
        users = repo.get_all(skip=0, limit=10000)
        if not users:
            print("No users found.")
            return 0

        print("Current users:")
        for user in users:
            print(
                f"- id={user.id} role={user.role} "
                f"twitch={user.twitch_username or '-'} "
                f"vk={user.vk_username or '-'} "
                f"vk_channel={user.vk_channel_name or '-'}"
            )
        return 0
    finally:
        db.close()


def resolve_target_ids(args: argparse.Namespace) -> list[int]:
    db = SessionLocal()
    try:
        repo = UserRepository(db)
        target_ids = set(args.user_id)

        for twitch_name in args.twitch:
            user = repo.get_by_twitch_username(twitch_name)
            if not user:
                raise SystemExit(f"Twitch user not found: {twitch_name}")
            target_ids.add(user.id)

        for vk_name in args.vk:
            user = repo.get_by_vk_username(vk_name)
            if not user:
                raise SystemExit(f"VK user not found: {vk_name}")
            target_ids.add(user.id)

        return sorted(target_ids)
    finally:
        db.close()


def print_preview(user_ids: list[int]) -> None:
    db = SessionLocal()
    try:
        if not user_ids:
            print("No target users were selected.")
            return

        for user_id in user_ids:
            preview = user_cleanup_service.preview_user_deletion(user_id, db)
            print()
            print(f"User {preview.user_id}: {preview.username} (role={preview.role})")
            if preview.channel_names:
                print(f"  channel names: {', '.join(preview.channel_names)}")
            if preview.platform_user_ids:
                print(f"  platform ids: {', '.join(preview.platform_user_ids)}")
            print(f"  total rows to delete: {preview.total_rows}")
            for table_name, count in preview.counts.items():
                if count:
                    print(f"    {table_name}: {count}")
    finally:
        db.close()


async def run_delete(user_ids: list[int]) -> None:
    db = SessionLocal()
    try:
        for user_id in user_ids:
            result = await user_cleanup_service.permanently_delete_user(user_id, db)
            print()
            print(result.message)
            for table_name, count in result.deleted_counts.items():
                if count:
                    print(f"  {table_name}: {count}")
    finally:
        db.close()


def main() -> int:
    if not os.getenv("DATABASE_URL"):
        print("DATABASE_URL is not set.")
        return 1

    args = parse_args()

    if args.list:
        return list_users()

    target_ids = resolve_target_ids(args)
    if not target_ids:
        print("Specify at least one target via --user-id, --twitch, or --vk.")
        return 1

    print_preview(target_ids)

    if not args.yes:
        print()
        print("This was only a dry-run. Run again with --yes to perform deletion.")
        return 0

    print()
    print("Deleting selected users...")
    asyncio.run(run_delete(target_ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
