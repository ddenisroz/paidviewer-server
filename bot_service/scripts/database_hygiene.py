#!/usr/bin/env python3
"""Preview and safely clean database garbage."""

from __future__ import annotations

import argparse
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
from services.database_cleanup_service import DatabaseCleanupService  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Preview and safely clean orphan rows, legacy session_id leftovers, "
            "and old inactive sessions."
        ),
    )
    parser.add_argument(
        "--orphan-users",
        action="store_true",
        help="Preview and optionally clean rows that reference a missing user_id.",
    )
    parser.add_argument(
        "--legacy-session-records",
        action="store_true",
        help="Clean legacy session_id rows in active user-only tables.",
    )
    parser.add_argument(
        "--inactive-sessions",
        action="store_true",
        help="Preview and optionally clean old inactive sessions.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all checks and cleanup operations at once.",
    )
    parser.add_argument(
        "--inactive-session-days",
        type=int,
        default=7,
        help="How many days to retain inactive sessions before deletion. Default: 7.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Perform the cleanup after the preview.",
    )
    return parser.parse_args()


def _selected_actions(args: argparse.Namespace) -> tuple[bool, bool, bool]:
    clean_orphans = args.all or args.orphan_users
    clean_legacy_sessions = args.all or args.legacy_session_records
    clean_sessions = args.all or args.inactive_sessions
    if not clean_orphans and not clean_legacy_sessions and not clean_sessions:
        return True, True, True
    return clean_orphans, clean_legacy_sessions, clean_sessions


def _print_table_preview(title: str, preview: dict) -> None:
    print(f"{title}:")
    print(f"  total rows to clean: {preview.get('total_rows', 0)}")
    for table_name, count in preview.get("tables", {}).items():
        if count:
            print(f"    {table_name}: {count}")


def _print_session_preview(preview: dict) -> None:
    print("Inactive sessions:")
    print(f"  retention: {preview.get('retention_days', 7)} days")
    print(f"  total sessions: {preview.get('total_sessions', 0)}")
    print(f"  active: {preview.get('active_sessions', 0)}")
    print(f"  inactive: {preview.get('inactive_sessions', 0)}")
    print(f"  to delete: {preview.get('old_inactive_sessions', 0)}")


def main() -> int:
    if not os.getenv("DATABASE_URL"):
        print("DATABASE_URL is not set.")
        return 1

    args = parse_args()
    clean_orphans, clean_legacy_sessions, clean_sessions = _selected_actions(args)

    db = SessionLocal()
    try:
        cleanup_service = DatabaseCleanupService(db)

        print("=== Preview database hygiene ===")
        if clean_orphans:
            orphan_preview = cleanup_service.preview_orphan_user_records()
            _print_table_preview("Orphan user rows", orphan_preview)
            print()

        if clean_legacy_sessions:
            legacy_preview = cleanup_service.preview_legacy_session_records()
            _print_table_preview("Legacy session_id rows", legacy_preview)
            print()

        if clean_sessions:
            session_preview = cleanup_service.preview_inactive_session_cleanup(args.inactive_session_days)
            _print_session_preview(session_preview)
            print()

        if not args.yes:
            print("Preview only. Run again with --yes to perform the cleanup.")
            return 0

        print("=== Running cleanup ===")
        if clean_orphans:
            orphan_result = cleanup_service.cleanup_orphan_user_records()
            print(f"Cleaned orphan rows: {orphan_result.get('total_rows', 0)}")
            for table_name, count in orphan_result.get("tables", {}).items():
                if count:
                    print(f"  {table_name}: {count}")

        if clean_legacy_sessions:
            legacy_result = cleanup_service.cleanup_legacy_session_records()
            print(f"Cleaned legacy session_id rows: {legacy_result.get('total_rows', 0)}")
            for table_name, count in legacy_result.get("tables", {}).items():
                if count:
                    print(f"  {table_name}: {count}")

        if clean_sessions:
            session_result = cleanup_service.cleanup_inactive_sessions(args.inactive_session_days)
            print(f"Cleaned old inactive sessions: {session_result.get('deleted_sessions', 0)}")

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
