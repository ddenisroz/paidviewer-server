#!/usr/bin/env python3
"""
Normalize admin-related data across legacy and current tables.

Source of truth:
- users.role ('admin' | 'user')

Compatibility:
- users.is_admin is kept in sync with users.role.
- admin_users is treated as legacy bootstrap mapping only.
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text

# Add project root to Python path
BOT_SERVICE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(BOT_SERVICE_ROOT))

# Load .env
env_path = BOT_SERVICE_ROOT / ".env"
load_dotenv(dotenv_path=env_path, override=True)

from core.database import SessionLocal  # noqa: E402


def _scalar(db, sql: str) -> int:
    return int(db.execute(text(sql)).scalar() or 0)


def show_summary(db) -> None:
    print("=== Admin Data Summary ===")
    total_users = _scalar(db, "SELECT COUNT(*) FROM users")
    role_admin = _scalar(db, "SELECT COUNT(*) FROM users WHERE role = 'admin'")
    flag_admin = _scalar(db, "SELECT COUNT(*) FROM users WHERE is_admin IS TRUE")
    mismatch_role_flag = _scalar(
        db,
        """
        SELECT COUNT(*) FROM users
        WHERE (role = 'admin' AND is_admin IS NOT TRUE)
           OR (role <> 'admin' AND is_admin IS TRUE)
        """,
    )
    invalid_roles = _scalar(
        db,
        """
        SELECT COUNT(*) FROM users
        WHERE role IS NULL OR role NOT IN ('admin', 'user')
        """,
    )
    legacy_admin_rows = _scalar(db, "SELECT COUNT(*) FROM admin_users")

    print(f"users.total={total_users}")
    print(f"users.role_admin={role_admin}")
    print(f"users.is_admin_true={flag_admin}")
    print(f"users.role_flag_mismatch={mismatch_role_flag}")
    print(f"users.invalid_roles={invalid_roles}")
    print(f"admin_users.rows={legacy_admin_rows}")
    print("==========================")


def normalize_admin_tables(apply_changes: bool) -> None:
    db = SessionLocal()
    try:
        print("Dry run mode:", not apply_changes)
        show_summary(db)

        # 1) Ensure role has only supported values.
        q_fix_invalid_roles = text(
            """
            UPDATE users
            SET role = CASE
                WHEN is_admin IS TRUE THEN 'admin'
                ELSE 'user'
            END
            WHERE role IS NULL OR role NOT IN ('admin', 'user')
            """
        )

        # 2) Promote users with legacy is_admin=true to role=admin.
        q_promote_from_flag = text(
            """
            UPDATE users
            SET role = 'admin'
            WHERE is_admin IS TRUE AND role <> 'admin'
            """
        )

        # 3) Promote users matched by legacy admin_users mapping.
        #    Mapping is via user_tokens(platform, platform_user_id) -> users.id.
        q_promote_from_legacy_table = text(
            """
            UPDATE users
            SET role = 'admin'
            WHERE EXISTS (
                SELECT 1
                FROM user_tokens ut
                JOIN admin_users au
                  ON au.platform = ut.platform
                 AND au.platform_user_id = ut.platform_user_id
                WHERE ut.user_id = users.id
                  AND COALESCE(au.is_active, TRUE) = TRUE
            )
            AND role <> 'admin'
            """
        )

        # 4) Keep legacy boolean in sync with role.
        q_sync_is_admin_true = text(
            """
            UPDATE users
            SET is_admin = TRUE
            WHERE role = 'admin' AND is_admin IS NOT TRUE
            """
        )
        q_sync_is_admin_false = text(
            """
            UPDATE users
            SET is_admin = FALSE
            WHERE role <> 'admin' AND is_admin IS TRUE
            """
        )

        if not apply_changes:
            print("No changes applied. Re-run with --apply to persist updates.")
            return

        r1 = db.execute(q_fix_invalid_roles).rowcount
        r2 = db.execute(q_promote_from_flag).rowcount
        r3 = db.execute(q_promote_from_legacy_table).rowcount
        r4 = db.execute(q_sync_is_admin_true).rowcount
        r5 = db.execute(q_sync_is_admin_false).rowcount
        db.commit()

        print("Applied updates:")
        print(f"  fix_invalid_roles={r1}")
        print(f"  promote_from_is_admin={r2}")
        print(f"  promote_from_admin_users={r3}")
        print(f"  sync_is_admin_true={r4}")
        print(f"  sync_is_admin_false={r5}")

        show_summary(db)

        rows = db.execute(
            text(
                """
                SELECT id, role, is_admin, twitch_username, vk_username
                FROM users
                WHERE role = 'admin' OR is_admin IS TRUE
                ORDER BY id
                """
            )
        ).fetchall()
        print("Admin users:")
        for row in rows:
            print(tuple(row))
    finally:
        db.close()


if __name__ == "__main__":
    apply_flag = "--apply"
    apply_changes = apply_flag in sys.argv
    normalize_admin_tables(apply_changes=apply_changes)
