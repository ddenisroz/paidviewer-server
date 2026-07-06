"""Bootstrap production database before starting the API server.

The historical migration tree does not contain a full initial schema migration.
For a brand-new database we create the current SQLAlchemy schema, seed baseline
data, and stamp Alembic heads. Existing databases still run normal migrations.
"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from models import SessionLocal, engine, init_db
from models.base import ensure_db_schema


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("bootstrap_database")


def _alembic_config() -> Config:
    root = Path(__file__).resolve().parents[1]
    return Config(str(root / "alembic.ini"))


def _table_exists(table_name: str) -> bool:
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def _bootstrap_empty_database() -> None:
    logger.info("Empty database detected. Creating schema from SQLAlchemy metadata.")
    ensure_db_schema()
    init_db(create_schema=False, strict=False)
    logger.info("Stamping Alembic heads for freshly created schema.")
    command.stamp(_alembic_config(), "heads", purge=True)


def _upgrade_existing_database() -> None:
    logger.info("Existing database detected. Running Alembic upgrade heads.")
    command.upgrade(_alembic_config(), "heads")
    init_db(create_schema=False, strict=False)


def main() -> None:
    with SessionLocal() as session:
        session.execute(text("SELECT 1"))

    if not _table_exists("users"):
        _bootstrap_empty_database()
    else:
        _upgrade_existing_database()

    logger.info("Database bootstrap complete.")


if __name__ == "__main__":
    main()
