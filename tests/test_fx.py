from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.services import fx

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
YESTERDAY = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")


@pytest.fixture
def provider(monkeypatch):
    calls = []

    async def fake(base, quote):
        calls.append((base, quote))
        return 0.5

    monkeypatch.setattr(fx, "fetch_rate", fake)
    return calls


async def test_same_currency_is_one_without_io(db, provider):
    assert await fx.get_rate(db, "EUR", "EUR") == 1.0
    assert provider == []


async def test_stored_rate_for_today_skips_provider(db, provider):
    assert await fx.get_rate(db, "USD", "EUR") == 0.9  # seeded by the db fixture
    assert provider == []


async def test_fetch_is_cached_per_day(db, provider):
    assert await fx.get_rate(db, "GBP", "EUR") == 0.5
    assert await fx.get_rate(db, "GBP", "EUR") == 0.5
    assert provider == [("GBP", "EUR")]
    assert await db.fx_rates.count_documents({"base": "GBP", "quote": "EUR", "date": TODAY}) == 1


async def test_outage_falls_back_to_latest_earlier_rate(db, monkeypatch):
    async def boom(base, quote):
        raise RuntimeError("down")

    monkeypatch.setattr(fx, "fetch_rate", boom)
    await db.fx_rates.insert_many([
        {"date": "2020-01-01", "base": "GBP", "quote": "EUR", "rate": 1.1},
        {"date": YESTERDAY, "base": "GBP", "quote": "EUR", "rate": 1.2},
    ])
    assert await fx.get_rate(db, "GBP", "EUR") == 1.2
    assert await db.fx_rates.count_documents({"base": "GBP", "date": TODAY}) == 0  # fallback not stored as today's


async def test_outage_without_history_is_none(db, monkeypatch):
    async def boom(base, quote):
        raise RuntimeError("down")

    monkeypatch.setattr(fx, "fetch_rate", boom)
    assert await fx.get_rate(db, "JPY", "EUR") is None


async def test_rates_to_base_always_includes_base(db, provider):
    r = await fx.rates_to_base(db, {"USD"})
    assert r == {"USD": 0.9, settings.base_currency: 1.0}


def test_convert():
    rates = {"USD": 0.9, "EUR": 1.0, "JPY": None}
    assert fx.convert(1000, "USD", rates) == 900
    assert fx.convert(0, "USD", rates) == 0          # zero is a price, not missing
    assert fx.convert(1001, "USD", {"USD": 0.5}) == 500  # banker's rounding via round()
    assert fx.convert(None, "USD", rates) is None
    assert fx.convert(100, "JPY", rates) is None      # unknown rate -> None, never 0
    assert fx.convert(100, "XXX", rates) is None
