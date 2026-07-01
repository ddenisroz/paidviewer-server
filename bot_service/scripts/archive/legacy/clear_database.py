#!/usr/bin/env python3
"""
Database backup/clear/restore helper.
"""

import argparse
import os
import shutil
import sys
from datetime import datetime

# Add bot_service root to Python path for local imports.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.project_paths import BACKUPS_DIR, DATA_DIR


def _backup_dir():
    path = BACKUPS_DIR / "database"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _list_backups(desc: bool = True):
    backup_dir = BACKUPS_DIR / "database"
    if not backup_dir.exists():
        return []
    return sorted(backup_dir.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=desc)


def clear_database(dry_run: bool = False) -> None:
    """Create a backup, then remove database and WAL/SHM side files."""
    db_path = DATA_DIR / "app_data.db"
    wal_path = db_path.with_suffix(".db-wal")
    shm_path = db_path.with_suffix(".db-shm")

    if not db_path.exists():
        print(f"[OK] Database file not found: {db_path}")
        print("[INFO] A fresh database will be created on next app start")
        return

    backup_dir = _backup_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"app_data_backup_{timestamp}.db"

    if dry_run:
        print("[DRY-RUN] Clear database preview mode. No files will be changed.")
        print(f"[DRY-RUN] Would create backup: {backup_path}")
        print(f"[DRY-RUN] Would delete database: {db_path}")
        if wal_path.exists():
            print(f"[DRY-RUN] Would delete WAL file: {wal_path}")
        if shm_path.exists():
            print(f"[DRY-RUN] Would delete SHM file: {shm_path}")
        return

    try:
        print("[BACKUP] Creating backup...")
        print(f"   Source: {db_path}")
        print(f"   Target: {backup_path}")
        shutil.copy2(db_path, backup_path)
        print("[OK] Backup created")

        print("\n[DELETE] Removing database...")
        os.remove(db_path)
        print("[OK] Database removed")

        if wal_path.exists():
            os.remove(wal_path)
            print(f"[OK] Removed: {wal_path.name}")

        if shm_path.exists():
            os.remove(shm_path)
            print(f"[OK] Removed: {shm_path.name}")

        backup_size_mb = backup_path.stat().st_size / (1024 * 1024)
        print("\n[OK] Database cleanup complete")
        print(f"[INFO] Backup saved to: {backup_path}")
        print(f"[STATS] Backup size: {backup_size_mb:.2f} MB")

        backups = _list_backups(desc=True)
        if len(backups) > 1:
            print(f"\n[INFO] Total backups: {len(backups)}")
            print("Recent 5:")
            for index, backup in enumerate(backups[:5], 1):
                backup_time = datetime.fromtimestamp(backup.stat().st_mtime)
                size_mb = backup.stat().st_size / (1024 * 1024)
                print(f"{index}. {backup.name} ({size_mb:.2f} MB) - {backup_time:%Y-%m-%d %H:%M:%S}")

    except Exception as error:
        print(f"[ERROR] Failed to clear database: {error}")
        sys.exit(1)


def restore_database(backup_name: str | None = None, dry_run: bool = False) -> None:
    """Restore app_data.db from backup file (latest by default)."""
    backups = _list_backups(desc=True)
    backup_dir = BACKUPS_DIR / "database"

    if not backup_dir.exists():
        print(f"[ERROR] Backup directory not found: {backup_dir}")
        return

    if not backups:
        print(f"[ERROR] No backups found in: {backup_dir}")
        return

    if backup_name:
        backup_path = backup_dir / backup_name
        if not backup_path.exists():
            print(f"[ERROR] Backup file not found: {backup_path}")
            return
    else:
        backup_path = backups[0]
        print(f"[BACKUP] Using latest backup: {backup_path.name}")

    db_path = DATA_DIR / "app_data.db"

    if dry_run:
        print("[DRY-RUN] Restore database preview mode. No files will be changed.")
        print(f"[DRY-RUN] Backup source: {backup_path}")
        print(f"[DRY-RUN] Target database: {db_path}")
        if db_path.exists():
            print("[DRY-RUN] Existing DB detected; safety backup would be created before restore")
        return

    try:
        if db_path.exists():
            backup_dir = _backup_dir()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            current_backup = backup_dir / f"app_data_before_restore_{timestamp}.db"
            shutil.copy2(db_path, current_backup)
            print(f"[BACKUP] Current DB backup created: {current_backup.name}")

        print("\n[RESTORE] Restoring database...")
        shutil.copy2(backup_path, db_path)
        print(f"[OK] Database restored from {backup_path.name}")

    except Exception as error:
        print(f"[ERROR] Failed to restore database: {error}")
        sys.exit(1)


def print_backups() -> None:
    backups = _list_backups(desc=True)
    backup_dir = BACKUPS_DIR / "database"

    if not backups:
        print(f"[ERROR] No backups found in {backup_dir}")
        return

    print(f"Found backups: {len(backups)}\n")
    for index, backup in enumerate(backups, 1):
        backup_time = datetime.fromtimestamp(backup.stat().st_mtime)
        backup_size = backup.stat().st_size / (1024 * 1024)
        print(f"{index}. {backup.name}")
        print(f"   Size: {backup_size:.2f} MB")
        print(f"   Date: {backup_time:%Y-%m-%d %H:%M:%S}")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Database maintenance helper")
    parser.add_argument(
        "action",
        choices=["clear", "restore", "list"],
        help="Action: clear (wipe DB), restore (from backup), list (show backups)",
    )
    parser.add_argument("--backup", help="Backup filename for restore action (default: latest backup)")
    parser.add_argument("--dry-run", action="store_true", help="Preview mode without changing files")
    parser.add_argument("--yes", action="store_true", help="Skip interactive confirmation for clear")

    args = parser.parse_args()

    if args.action == "clear":
        if args.dry_run:
            clear_database(dry_run=True)
            sys.exit(0)

        if not args.yes:
            print("[WARN] This will create a backup and then DELETE the database file.")
            response = input("Continue? (yes/no): ").strip().lower()
            if response not in {"yes", "y", "да", "д"}:
                print("[INFO] Operation cancelled")
                sys.exit(0)

        clear_database()
    elif args.action == "restore":
        restore_database(args.backup, dry_run=args.dry_run)
    elif args.action == "list":
        print_backups()
