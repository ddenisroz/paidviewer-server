# models/base.py
"""
SQLAlchemy base configuration: engine, SessionLocal, Base.
"""

import logging
import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from core.config import settings

logger = logging.getLogger(__name__)


# Resolve database URL from settings
DATABASE_URL = (settings.database_url or "").strip().strip('"').strip("'")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required. Please set it in .env file.")

# Determine environment flags
IS_TESTING = os.getenv("TESTING", "false").lower() == "true" or getattr(settings, "testing", False)
IS_POSTGRESQL = DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgresql+psycopg2://")

if not IS_POSTGRESQL and not IS_TESTING:
    raise ValueError(f"Only PostgreSQL is supported. Current DATABASE_URL: {DATABASE_URL[:50]}...")


def _create_test_engine(db_url: str):
    if IS_TESTING:
        from sqlalchemy.pool import StaticPool

        return create_engine(
            db_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )

    return create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        echo=False,
    )


def _create_postgres_engine(db_url: str):
    return create_engine(
        db_url,
        pool_size=20,
        max_overflow=40,
        pool_pre_ping=True,
        pool_recycle=3600,
        pool_reset_on_return="commit",
        echo=False,
        connect_args={
            "connect_timeout": 10,
            "application_name": "bot_service",
            "options": "-c statement_timeout=30000",
        },
    )


if IS_TESTING:
    engine = _create_test_engine(DATABASE_URL)
else:
    engine = _create_postgres_engine(DATABASE_URL)


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


@contextmanager
def db_session():
    """Context manager for DB session with automatic commit/rollback/close."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def ensure_db_schema():
    """Create DB schema from SQLAlchemy metadata."""
    if engine is None:
        logger.error("[ERROR] Database engine is not configured")
        raise RuntimeError("Database engine is not configured")

    try:
        Base.metadata.create_all(bind=engine)
        logger.info("[DB] Schema create/update completed via SQLAlchemy metadata")
    except UnicodeDecodeError as exc:
        logger.error("[ERROR] PostgreSQL connection failed while initializing schema: %s", exc)
        raise RuntimeError(
            "PostgreSQL connection failed (possible invalid DATABASE_URL or unreachable PostgreSQL server)."
        ) from exc


def init_db(*, create_schema: bool = False, strict: bool = True):
    """Seed baseline data, optionally creating schema for local tooling."""
    from constants import DEFAULT_BLOCKED_BOTS
    from models.drops import DropsQuality
    from models.moderation import BlockedBot

    if create_schema:
        ensure_db_schema()

    default_qualities = [
        {"name": "Common", "color": "#9ca3af", "weight": 100},
        {"name": "Rare", "color": "#3b82f6", "weight": 50},
        {"name": "Epic", "color": "#a855f7", "weight": 20},
        {"name": "Legendary", "color": "#eab308", "weight": 5},
        {"name": "Mythical", "color": "#ef4444", "weight": 1},
    ]

    db = SessionLocal()
    try:
        existing_bots = {bot.bot_name.lower() for bot in db.query(BlockedBot).all()}
        for bot_name in DEFAULT_BLOCKED_BOTS:
            if bot_name.lower() not in existing_bots:
                db.add(BlockedBot(bot_name=bot_name.lower()))

        existing_qualities = {q.name for q in db.query(DropsQuality).all()}
        for quality_data in default_qualities:
            if quality_data["name"] not in existing_qualities:
                db.add(DropsQuality(**quality_data))

        db.commit()
        logger.info("[DB] Database seeding complete (blocked bots + lootbox qualities)")
    except Exception as e:
        logger.error(f"Error during database seeding: {e}")
        db.rollback()
        if strict:
            raise
    finally:
        db.close()

    logger.info("Database initialized")
