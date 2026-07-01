#!/usr/bin/env python3
"""Read-only diagnostics for user/account growth and duplicate identities."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text


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


def _scalar(db, sql: str, params: dict[str, Any] | None = None) -> int:
    return int(db.execute(text(sql), params or {}).scalar() or 0)


def _rows(db, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return [dict(row) for row in db.execute(text(sql), params or {}).mappings().all()]


def build_report(db) -> dict[str, Any]:
    duplicate_identities = _rows(
        db,
        """
        SELECT platform, platform_user_id, COUNT(*) AS token_count,
               COUNT(DISTINCT user_id) AS linked_users
        FROM user_tokens
        WHERE user_id IS NOT NULL
          AND platform_user_id IS NOT NULL
          AND platform_user_id <> ''
        GROUP BY platform, platform_user_id
        HAVING COUNT(*) > 1
        ORDER BY token_count DESC, platform ASC
        """,
    )

    users = {
        "total": _scalar(db, "SELECT COUNT(*) FROM users"),
        "active": _scalar(db, "SELECT COUNT(*) FROM users WHERE is_active IS TRUE"),
        "inactive": _scalar(db, "SELECT COUNT(*) FROM users WHERE is_active IS NOT TRUE"),
        "admins": _scalar(db, "SELECT COUNT(*) FROM users WHERE is_admin IS TRUE"),
        "blocked": _scalar(db, "SELECT COUNT(*) FROM users WHERE is_blocked IS TRUE"),
    }
    sessions = {
        "total": _scalar(db, "SELECT COUNT(*) FROM user_sessions"),
        "active": _scalar(db, "SELECT COUNT(*) FROM user_sessions WHERE is_active IS TRUE"),
        "linked_users": _scalar(db, "SELECT COUNT(DISTINCT user_id) FROM user_sessions WHERE user_id IS NOT NULL"),
    }

    return {
        "mode": "read_only",
        "automatic_deletes": False,
        "users": users,
        "sessions": sessions,
        "tokens_by_platform": _rows(
            db,
            """
            SELECT platform, COUNT(*) AS token_count, COUNT(DISTINCT user_id) AS linked_users
            FROM user_tokens
            GROUP BY platform
            ORDER BY token_count DESC, platform ASC
            """,
        ),
        "duplicate_identities": duplicate_identities,
        "commands": {
            "total": _scalar(db, "SELECT COUNT(*) FROM bot_commands"),
            "global": _scalar(db, "SELECT COUNT(*) FROM bot_commands WHERE user_id IS NULL"),
            "disabled": _scalar(db, "SELECT COUNT(*) FROM bot_commands WHERE is_enabled IS NOT TRUE"),
        },
        "dry_run_cleanup": {
            "would_delete_users": 0,
            "duplicate_identity_groups_to_resolve": len(duplicate_identities),
            "note": "No rows are modified by this script.",
        },
    }


def main() -> int:
    if not os.getenv("DATABASE_URL"):
        print("DATABASE_URL is not set.", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        report = build_report(db)
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
