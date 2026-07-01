from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import ClassVar

import httpx

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CurrencyConversion:
    amount_rub: float
    rate: float
    rate_source: str
    rate_timestamp: datetime


class CurrencyRateService:
    """Convert supported donation currencies to RUB using Frankfurter with safe fallbacks."""

    API_BASE = "https://api.frankfurter.dev"
    TTL_SECONDS = 6 * 60 * 60
    STATIC_RUB_RATES: ClassVar[dict[str, float]] = {
        "USD": 90.0,
        "EUR": 100.0,
    }
    _cache: ClassVar[dict[str, tuple[float, float, datetime]]] = {}

    async def convert_to_rub(self, amount: float, currency: str | None) -> CurrencyConversion:
        normalized_currency = (currency or "RUB").strip().upper()
        if normalized_currency in {"", "RUB", "RUR"}:
            return CurrencyConversion(
                amount_rub=round(float(amount), 2),
                rate=1.0,
                rate_source="identity",
                rate_timestamp=datetime.now(timezone.utc),
            )

        rate, source, timestamp = await self._get_rub_rate(normalized_currency)
        return CurrencyConversion(
            amount_rub=round(float(amount) * rate, 2),
            rate=rate,
            rate_source=source,
            rate_timestamp=timestamp,
        )

    async def _get_rub_rate(self, currency: str) -> tuple[float, str, datetime]:
        cached = self._cache.get(currency)
        now = time.time()
        if cached and now - cached[1] <= self.TTL_SECONDS:
            return cached[0], "frankfurter_cache", cached[2]

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=4.0), trust_env=False) as client:
                response = await client.get(f"{self.API_BASE}/v2/rate/{currency}/RUB")
                response.raise_for_status()
                payload = response.json()
            rate = float(payload.get("rate") or 0)
            if rate <= 0:
                raise ValueError(f"Frankfurter returned invalid RUB rate for {currency}: {payload!r}")
            timestamp = datetime.now(timezone.utc)
            self._cache[currency] = (rate, now, timestamp)
            logger.info("Currency rate loaded source=frankfurter currency=%s rate_to_rub=%s", currency, rate)
            return rate, "frankfurter", timestamp
        except Exception as exc:
            if cached:
                logger.warning("Currency rate fallback to cached source currency=%s error=%s", currency, exc)
                return cached[0], "frankfurter_cache_stale", cached[2]
            if currency in self.STATIC_RUB_RATES:
                logger.warning("Currency rate fallback to static source currency=%s error=%s", currency, exc)
                return self.STATIC_RUB_RATES[currency], "static_fallback", datetime.now(timezone.utc)
            raise
