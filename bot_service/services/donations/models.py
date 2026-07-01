from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(slots=True)
class DonationEvent:
    provider: str
    event_id: str
    provider_user_id: str
    donor_name: str
    donor_id: str
    message: str
    amount_original: float
    currency_original: str
    amount_rub: float
    rate_source: str
    rate_timestamp: datetime


class DonationProvider:
    provider_name = "unknown"

    async def normalize_event(self, payload: dict) -> DonationEvent:
        raise NotImplementedError


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
