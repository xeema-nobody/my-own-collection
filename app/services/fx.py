"""FX rates cached per day in Mongo; falls back to latest stored rate if the API is down."""
import logging
from datetime import datetime, timezone

from app.config import settings
from app.providers.price.fx import fetch_rate

log = logging.getLogger(__name__)


async def get_rate(db, base: str, quote: str) -> float | None:
    if base == quote:
        return 1.0
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    doc = await db.fx_rates.find_one({"date": today, "base": base, "quote": quote})
    if doc:
        return doc["rate"]
    try:
        rate = await fetch_rate(base, quote)
        await db.fx_rates.update_one({"date": today, "base": base, "quote": quote},
                                     {"$set": {"rate": rate}}, upsert=True)
        return rate
    except Exception as e:  # noqa: BLE001 - FX outage must not break refresh
        log.warning("fx fetch failed %s->%s: %s", base, quote, e)
        last = await db.fx_rates.find_one({"base": base, "quote": quote}, sort=[("date", -1)])
        return last["rate"] if last else None


async def rates_to_base(db, currencies: set[str]) -> dict[str, float | None]:
    return {c: await get_rate(db, c, settings.base_currency) for c in currencies | {settings.base_currency}}


def convert(cents: int | None, currency: str, rates: dict[str, float | None]) -> int | None:
    rate = rates.get(currency)
    if cents is None or rate is None:
        return None
    return round(cents * rate)
