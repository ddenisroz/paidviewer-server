#!/usr/bin/env python3
"""
Reset database by dropping all tables and recreating schema/seed data.
"""

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

# Add bot_service root for local imports.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from models.base import Base, engine, init_db  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def reset_database(dry_run: bool = False) -> None:
    """Drop and recreate all tables."""
    if dry_run:
        table_names = sorted(Base.metadata.tables.keys())
        logger.info("[DRY-RUN] Reset database preview mode. No changes will be made.")
        logger.info(
            "[DRY-RUN] Tables that would be dropped: %s",
            ", ".join(table_names) if table_names else "(no mapped tables found)",
        )
        logger.info("[DRY-RUN] Would call init_db(create_schema=True) to recreate schema and seed data")
        return

    logger.info("[RESET] Dropping all tables...")
    Base.metadata.drop_all(bind=engine)
    logger.info("[OK] All tables dropped")

    logger.info("[RESET] Recreating schema and seed data...")
    init_db(create_schema=True, strict=True)
    logger.info("[OK] Database reset complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reset app database")
    parser.add_argument("--dry-run", action="store_true", help="Preview mode without changing the database")
    parser.add_argument("--yes", action="store_true", help="Skip interactive confirmation")
    args = parser.parse_args()

    if args.dry_run:
        reset_database(dry_run=True)
        sys.exit(0)

    if not args.yes:
        print("[WARN] This will DELETE ALL DATA from the database and recreate schema.")
        confirm = input("Continue? (yes/no): ").strip().lower()
        if confirm not in {"yes", "y", "да", "д"}:
            logger.info("[INFO] Operation cancelled")
            sys.exit(0)

    reset_database()
