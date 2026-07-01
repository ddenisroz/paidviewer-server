"""Date and time utilities with timezone-safe UTC helpers."""
from datetime import datetime, timezone, timedelta
from typing import Optional


def utcnow() -> datetime:
    """
    Return the current UTC time as a timezone-aware value.
    """
    return datetime.now(timezone.utc)


def utcnow_naive() -> datetime:
    """
    Return the current UTC time without timezone info.

    Use this only for backward compatibility with legacy code.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_utc(dt: datetime) -> datetime:
    """
    Convert ``dt`` to a timezone-aware UTC datetime.
    """
    if dt.tzinfo is None:
        # Assume naive values are already in UTC.
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def from_timestamp(timestamp: float) -> datetime:
    """
    Create a timezone-aware UTC datetime from a Unix timestamp.
    """
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def to_timestamp(dt: datetime) -> float:
    """
    Convert ``dt`` to a Unix timestamp.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def add_time(
    dt: Optional[datetime] = None,
    days: int = 0,
    hours: int = 0,
    minutes: int = 0,
    seconds: int = 0
) -> datetime:
    """
    Add a time delta to ``dt`` or the current UTC time.
    """
    if dt is None:
        dt = utcnow()

    delta = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
    return dt + delta


def is_expired(dt: datetime) -> bool:
    """
    Return ``True`` when ``dt`` is in the past.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt < utcnow()


def format_iso(dt: datetime) -> str:
    """
    Format ``dt`` as an ISO 8601 string.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def parse_iso(iso_string: str) -> datetime:
    """
    Parse an ISO 8601 string into a datetime.
    """
    dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def get_date_key(dt: Optional[datetime] = None, format: str = "daily") -> str:
    """
    Return a date grouping key for the requested resolution.
    """
    if dt is None:
        dt = utcnow()

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    if format == "daily":
        return dt.strftime("%Y-%m-%d")
    elif format == "weekly":
        # ISO week (Monday is the first day).
        return dt.strftime("%Y-W%V")
    elif format == "monthly":
        return dt.strftime("%Y-%m")
    elif format == "yearly":
        return dt.strftime("%Y")
    else:
        raise ValueError(f"Unknown format: {format}")

