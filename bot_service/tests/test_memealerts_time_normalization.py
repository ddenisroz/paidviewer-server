from datetime import datetime

from services.memealerts_service import MemeAlertsService


def test_safe_iso_normalizes_naive_datetime_to_utc():
    value = datetime(2026, 6, 26, 10, 15, 30)

    normalized = MemeAlertsService._safe_iso(value)

    assert normalized == "2026-06-26T10:15:30+00:00"


def test_normalize_supporter_timestamp_normalizes_parseable_iso_strings_to_utc():
    normalized = MemeAlertsService._normalize_supporter_timestamp(
        {"createdAt": "2026-06-26T15:30:00+05:00"}
    )

    assert normalized == "2026-06-26T10:30:00+00:00"


def test_normalize_supporter_timestamp_treats_naive_iso_strings_as_utc():
    normalized = MemeAlertsService._normalize_supporter_timestamp(
        {"createdAt": "2026-06-26T10:30:00"}
    )

    assert normalized == "2026-06-26T10:30:00+00:00"
