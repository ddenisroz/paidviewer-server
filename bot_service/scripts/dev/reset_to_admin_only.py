#!/usr/bin/env python3
"""Preview or delete all non-admin users while keeping admin accounts."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

BOT_SERVICE_ROOT = Path(__file__).resolve().parents[2]
if str(BOT_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(BOT_SERVICE_ROOT))

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

if load_dotenv:
    load_dotenv(BOT_SERVICE_ROOT / ".env", override=False)

from sqlalchemy import or_  # noqa: E402

from models import SessionLocal  # noqa: E402
from models.user import User  # noqa: E402
from services.user_cleanup_service import user_cleanup_service  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Delete every non-admin user while keeping admin accounts.",
    )
    parser.add_argument("--yes", action="store_true", help="Perform deletion after the preview.")
    return parser.parse_args()


def describe_user(user: User) -> str:
    username = user.twitch_username or user.vk_username or user.vk_channel_name or f"user_{user.id}"
    return f"id={user.id} role={user.role} username={username}"


def load_users() -> tuple[list[User], list[User]]:
    db = SessionLocal()
    try:
        admins = (
            db.query(User)
            .filter(or_(User.role == "admin", User.is_admin.is_(True)))
            .order_by(User.id.asc())
            .all()
        )
        targets = (
            db.query(User)
            .filter(~or_(User.role == "admin", User.is_admin.is_(True)))
            .order_by(User.id.asc())
            .all()
        )
        return admins, targets
    finally:
        db.close()


def print_preview(targets: list[User]) -> None:
    db = SessionLocal()
    try:
        if not targets:
            print("No non-admin users found.")
            return

        print("Users scheduled for deletion:")
        for user in targets:
            preview = user_cleanup_service.preview_user_deletion(user.id, db)
            print(f"- {describe_user(user)} | rows={preview.total_rows}")
    finally:
        db.close()


async def run_delete(target_ids: list[int]) -> None:
    db = SessionLocal()
    try:
        for user_id in target_ids:
            result = await user_cleanup_service.permanently_delete_user(user_id, db)
            print(result.message)
    finally:
        db.close()


def main() -> int:
    args = parse_args()
    admins, targets = load_users()

    if not admins:
        print("Abort: no admin users found.")
        return 1

    print("Admins kept:")
    for admin in admins:
        print(f"- {describe_user(admin)}")

    print()
    print_preview(targets)

    if not args.yes:
        print()
        print("Dry-run only. Run again with --yes to delete all non-admin users.")
        return 0

    if not targets:
        print()
        print("Nothing to delete.")
        return 0

    print()
    print("Deleting non-admin users...")
    asyncio.run(run_delete([user.id for user in targets]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
