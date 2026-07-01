from __future__ import annotations

from .currency_rate_service import CurrencyRateService
from .models import DonationEvent, DonationProvider


def _safe_amount(value: object) -> float:
    try:
        return float(str(value or 0).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


class DonationAlertsProvider(DonationProvider):
    provider_name = "donationalerts"

    def __init__(self, currency_rates: CurrencyRateService | None = None) -> None:
        self.currency_rates = currency_rates or CurrencyRateService()

    async def normalize_event(self, payload: dict) -> DonationEvent:
        amount_original = _safe_amount(payload.get("amount"))
        currency_original = str(payload.get("currency") or "RUB").strip().upper() or "RUB"
        conversion = await self.currency_rates.convert_to_rub(amount_original, currency_original)
        donor_name = str(payload.get("username") or payload.get("name") or "Anonymous")
        donor_id = str(payload.get("donor_id") or payload.get("username") or "unknown")
        provider_user_id = str(payload.get("user_id") or payload.get("streamer_id") or "")
        message = str(payload.get("message") or "")
        event_id = str(payload.get("id") or payload.get("alert_id") or payload.get("uuid") or "").strip()
        if not event_id:
            event_id = f"{provider_user_id or 'unknown'}:{donor_name}:{amount_original}:{payload.get('created_at') or payload.get('date') or message}"

        return DonationEvent(
            provider=self.provider_name,
            event_id=event_id,
            provider_user_id=provider_user_id,
            donor_name=donor_name,
            donor_id=donor_id,
            message=message,
            amount_original=amount_original,
            currency_original=currency_original,
            amount_rub=conversion.amount_rub,
            rate_source=conversion.rate_source,
            rate_timestamp=conversion.rate_timestamp,
        )
