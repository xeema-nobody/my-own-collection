from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from app.main import app
from app.providers.fetcher import FetcherUnavailable
from app.providers.price.base import AdapterResult, Candidate
from app.services import matching
from app.services import price_fetch as pf
from app.services.pricing import get_rates, store_card_prices, store_scraped_points
from tests.conftest import make_card

PC_URL = "https://www.pricecharting.com/game/pokemon-x/mew-ex-205"


def pt(source, grade="raw", market=1000, as_of=None, kind="market"):
    return {"source": source, "kind": kind, "grade_key": grade, "variant": None, "currency": "USD",
            "as_of": as_of, "market": market, "low": None, "avg": None, "median": None, "high": None,
            "sample_size": None, "url": None}


class FakeProvider:
    def __init__(self, source, results=None, default=None):
        self.source, self.results, self.calls = source, results or {}, []
        self.default = default or AdapterResult("ok", points=[pt(source)], url=PC_URL)

    async def fetch(self, card, client, known_url=None, today=None):
        self.calls.append((card["_id"], known_url))
        r = self.results.get(card["_id"], self.default)
        if isinstance(r, Exception):
            raise r
        return r


class FakeClient:
    def __init__(self, sites=None, down=False):
        self.sites, self.down = sites or {}, down

    async def status(self):
        if self.down:
            raise FetcherUnavailable("down")
        return {"browser": "up", "sites": self.sites}


def providers(**by_source):
    return lambda s: by_source[s]


async def seed(db, *nums):
    for n in nums:
        await db.cards.insert_one(make_card("sv3pt5", n))
    return [f"pokemon:sv3pt5-{n}" for n in nums]


async def test_resolve_targets_dedupes_in_order(db):
    ids = await seed(db, "1", "2", "3")
    await db.cards.insert_one(make_card("other", "9"))
    await db.collection_items.insert_one({"stack_key": "k", "card_id": ids[2]})
    out = await pf.resolve_targets(db, [ids[2], "pokemon:nope-1"], ["sv3pt5"], True)
    assert out == [ids[2], ids[0], ids[1]]


async def test_stores_points_and_logs(db):
    [c] = await seed(db, "1")
    p = FakeProvider("pricecharting", default=AdapterResult("ok", points=[
        pt("pricecharting", "G9", as_of=date(2026, 10, 1), kind="sold")], url=PC_URL))
    stats = await pf.fetch_prices([c], ["pricecharting"], provider_for=providers(pricecharting=p), client=FakeClient())
    assert stats["ok"] == 1 and stats["done"] == stats["total"] == 1
    obs = await db.prices.find_one({"source": "pricecharting"})
    assert obs["as_of"] == datetime(2026, 10, 1, tzinfo=timezone.utc)
    card = await db.cards.find_one({"_id": c})
    assert card["latest_price"]["pricecharting"]["sold"]["G9"]["_"]["market"] == 1000
    assert (await db.fetch_log.find_one({"_id": f"{c}|pricecharting"}))["status"] == "ok"
    assert (await db.jobs.find_one({"type": "price_fetch"}))["status"] == "ok"
    assert await db.collection_snapshots.count_documents({}) == 1


async def test_pair_isolation(db):
    a, b = await seed(db, "1", "2")
    p = FakeProvider("pricecharting", {a: RuntimeError("boom")})
    stats = await pf.fetch_prices([a, b], ["pricecharting"], provider_for=providers(pricecharting=p), client=FakeClient())
    assert stats["failed"] == 1 and stats["ok"] == 1 and stats["failures"][0]["card_id"] == a
    assert (await db.jobs.find_one({"type": "price_fetch"}))["status"] == "partial"


async def test_cache_skip_and_force(db):
    [c] = await seed(db, "1")
    p = FakeProvider("pricecharting")
    kw = dict(provider_for=providers(pricecharting=p), client=FakeClient())
    await pf.fetch_prices([c], ["pricecharting"], **kw)
    s2 = await pf.fetch_prices([c], ["pricecharting"], **kw)
    assert s2["skipped_cached"] == 1 and len(p.calls) == 1
    await db.fetch_log.update_one({}, {"$set": {"fetched_at": datetime.now(timezone.utc) - timedelta(hours=25)}})
    await pf.fetch_prices([c], ["pricecharting"], **kw)
    assert len(p.calls) == 2
    await pf.fetch_prices([c], ["pricecharting"], force=True, **kw)
    assert len(p.calls) == 3


async def test_needs_match_recorded_and_user_url_passed(db):
    [c] = await seed(db, "1")
    cand = Candidate(url=PC_URL, title="t", name="Mew ex", set_name="s", number="205", score=0.5)
    p = FakeProvider("pricecharting", default=AdapterResult("needs_match", candidates=[cand]))
    kw = dict(client=FakeClient())
    stats = await pf.fetch_prices([c], ["pricecharting"], provider_for=providers(pricecharting=p), **kw)
    assert stats["needs_match"] == 1 and stats["failed"] == 0
    assert stats["needs_match_list"] == [{"card_id": c, "source": "pricecharting"}]
    assert (await matching.get_matches(db, c))["pricecharting"]["candidates"][0]["url"] == PC_URL
    await matching.confirm(db, c, "pricecharting", PC_URL)
    await pf.fetch_prices([c], ["pricecharting"], provider_for=providers(pricecharting=p), **kw)
    assert p.calls[-1] == (c, PC_URL)
    # needs_match is not cached as fresh
    assert len(p.calls) == 2


async def test_login_timeout_skips_site_only(db):
    a, b = await seed(db, "1", "2")
    pc = FakeProvider("pricecharting", default=AdapterResult("login_timeout", detail="no login"))
    alt = FakeProvider("altxyz")
    stats = await pf.fetch_prices([a, b], ["pricecharting", "altxyz"],
                                  provider_for=providers(pricecharting=pc, altxyz=alt), client=FakeClient())
    assert len(pc.calls) == 1 and len(alt.calls) == 2
    assert stats["skipped_site"] == 1 and stats["failed"] == 1 and stats["ok"] == 2
    assert stats["done"] == stats["total"] == 4
    assert await db.alert_events.count_documents({"type": "system"}) == 0     # manual run: no inbox item


async def test_scheduled_login_needed_raises_one_inbox_item(db):
    a, b = await seed(db, "1", "2")
    pc = FakeProvider("pricecharting", default=AdapterResult("login_timeout", detail="no login"))
    await pf.fetch_prices([a, b], ["pricecharting"], provider_for=providers(pricecharting=pc),
                          client=FakeClient(), trigger="scheduler")
    [e] = await db.alert_events.find({"type": "system"}).to_list(None)
    assert "pricecharting" in e["rule"] and "login" in e["rule"] and e["read"] is False


async def test_fetcher_down_aborts_job(db):
    a, b = await seed(db, "1", "2")
    pc = FakeProvider("pricecharting", default=AdapterResult("error", detail="x"))
    stats = await pf.fetch_prices([a, b], ["pricecharting", "altxyz"], provider_for=providers(
        pricecharting=pc, altxyz=FakeProvider("altxyz")), client=FakeClient(down=True))
    job = await db.jobs.find_one({"type": "price_fetch"})
    assert job["status"] == "error" and job["error"] == "fetcher unreachable"
    assert len(pc.calls) == 1 and stats["done"] == stats["total"] == 4


async def test_cardmarket_web_waiting_login_maps_site(db):
    stats = {"waiting_login": []}
    import asyncio
    client = FakeClient({"cardmarket": "waiting_login:cardmarket", "altxyz": "idle"})
    pf.STATUS_POLL_S, old = 0.01, pf.STATUS_POLL_S
    try:
        [jid] = [(await db.jobs.insert_one({"type": "x", "status": "running"})).inserted_id]
        t = asyncio.create_task(pf._watch_login(db, jid, client, stats))
        await asyncio.sleep(0.1)
        t.cancel()
    finally:
        pf.STATUS_POLL_S = old
    assert stats["waiting_login"] == ["cardmarket_web"]


async def test_scraped_store_merges_and_survives_catalog_refresh(db):
    rates = await get_rates(db)
    card = make_card("a", "1")
    await db.cards.insert_one(card)
    await store_card_prices(db, card, rates)
    before = (await db.cards.find_one({"_id": card["_id"]}))["price_base"]
    n = await store_scraped_points(db, card["_id"], [pt("altxyz", "PSA9", 5000, date(2026, 10, 1), "sold")])
    n += await store_scraped_points(db, card["_id"], [pt("altxyz", "PSA9", 5100, date(2026, 10, 2), "sold")])
    assert n == 2 and await db.prices.count_documents({"source": "altxyz"}) == 1   # same-day overwrite
    c = await db.cards.find_one({"_id": card["_id"]})
    assert c["latest_price"]["altxyz"]["sold"]["PSA9"]["_"]["market"] == 5100
    assert "cardmarket" in c["latest_price"] and c["price_base"] == before
    await store_card_prices(db, card, rates)   # catalog refresh keeps scraped data
    c = await db.cards.find_one({"_id": card["_id"]})
    assert c["latest_price"]["altxyz"]["sold"]["PSA9"]["_"]["market"] == 5100
    assert c["latest_price"]["tcgplayer"]


# --- API ---

@pytest.fixture
async def client(db):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


@pytest.fixture
def fetcher_up(monkeypatch):
    calls = []

    async def fake(card_ids, sources=None, force=False, **kw):
        calls.append((card_ids, sources, force))

    async def status(self):
        return {"sites": {}}
    monkeypatch.setattr("app.providers.fetcher.FetcherClient.status", status)
    monkeypatch.setattr("app.api.admin.fetch_prices", fake)
    monkeypatch.setattr("app.api.cards.fetch_prices", fake)
    return calls


async def test_api_fetch_202_and_422(client, db, fetcher_up):
    ids = await seed(db, "1", "2")
    r = await client.post("/api/admin/prices/fetch", json={"cards": ids, "sources": ["altxyz"]})
    assert r.status_code == 202 and r.json() == {"started": True, "cards": 2}
    for body in ({}, {"cards": ids, "sources": ["tcgplayer"]}, {"cards": ["pokemon:nope-1"]}):
        assert (await client.post("/api/admin/prices/fetch", json=body)).status_code == 422


async def test_api_fetch_503_when_fetcher_down(client, db, monkeypatch):
    [c] = await seed(db, "1")

    async def status(self):
        raise FetcherUnavailable("nope")
    monkeypatch.setattr("app.providers.fetcher.FetcherClient.status", status)
    r = await client.post("/api/admin/prices/fetch", json={"cards": [c]})
    assert r.status_code == 503
    assert await db.jobs.count_documents({}) == 0


async def test_api_card_shortcut(client, db, fetcher_up):
    [c] = await seed(db, "1")
    r = await client.post(f"/api/cards/{c}/fetch-prices", json={"force": True})
    assert r.status_code == 202
    r2 = await client.post(f"/api/cards/{c}/fetch-prices")
    assert r2.status_code == 202
    assert (await client.post("/api/cards/pokemon:nope-1/fetch-prices")).status_code == 404


async def test_fetch_status_per_source(client, db):
    c = (await seed(db, "1"))[0]
    r = await client.get(f"/api/cards/{c}/fetch-status")
    assert r.status_code == 200 and r.json() == {"pricecharting": None, "cardmarket_web": None, "altxyz": None}
    await db.fetch_log.insert_one({"_id": f"{c}|altxyz", "card_id": c, "source": "altxyz", "status": "not_found",
                                   "detail": "no tiles", "url": None, "fetched_at": datetime.now(timezone.utc)})
    got = (await client.get(f"/api/cards/{c}/fetch-status")).json()
    assert got["pricecharting"] is None
    assert (got["altxyz"]["status"], got["altxyz"]["detail"]) == ("not_found", "no tiles")
    assert got["altxyz"]["fetched_at"]
    assert (await client.get("/api/cards/pokemon:nope-1/fetch-status")).status_code == 404


async def test_fetcher_status_up_and_down(client, monkeypatch):
    async def up(self):
        return {"browser": "up", "sites": {"altxyz": "idle"}, "last_error": None}

    async def down(self):
        raise FetcherUnavailable("fetcher unreachable")
    monkeypatch.setattr("app.providers.fetcher.FetcherClient.status", up)
    assert (await client.get("/api/admin/fetcher-status")).json() == {
        "up": True, "browser": "up", "sites": {"altxyz": "idle"}, "last_error": None}
    monkeypatch.setattr("app.providers.fetcher.FetcherClient.status", down)
    r = await client.get("/api/admin/fetcher-status")
    assert r.status_code == 200 and r.json() == {"up": False, "detail": "fetcher unreachable"}


async def test_stalest_owned_orders_caps_and_resumes(db):
    ids = await seed(db, "1", "2", "3", "4")
    for c in ids:
        await db.collection_items.insert_one({"stack_key": c, "card_id": c})
    now = datetime.now(timezone.utc)
    await db.fetch_log.insert_one({"_id": f"{ids[0]}|pricecharting", "card_id": ids[0], "status": "ok",
                                   "fetched_at": now - timedelta(days=1)})
    await db.fetch_log.insert_one({"_id": f"{ids[1]}|pricecharting", "card_id": ids[1], "status": "needs_match",
                                   "fetched_at": now - timedelta(days=3)})
    first = await pf.stalest_owned(db, 3)
    assert first == [ids[2], ids[3], ids[1]]          # never tried first (id order), then oldest
    for c in first:                                   # run done -> next run resumes with the rest
        await db.fetch_log.update_one({"_id": f"{c}|pricecharting"}, {"$set": {"card_id": c, "fetched_at": now}}, upsert=True)
    assert await pf.stalest_owned(db, 3) == [ids[0], ids[1], ids[2]]


async def test_trigger_stored_on_fetch_job(db):
    [c] = await seed(db, "1")
    p = FakeProvider("pricecharting")
    await pf.fetch_prices([c], ["pricecharting"], provider_for=providers(pricecharting=p), client=FakeClient(),
                          trigger="scheduler")
    assert (await db.jobs.find_one({"type": "price_fetch"}))["trigger"] == "scheduler"
