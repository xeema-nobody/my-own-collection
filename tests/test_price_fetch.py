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
    await own(db, c)   # owned: the run snapshots
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
    [nm] = stats["needs_match_list"]
    assert (nm["card_id"], nm["source"], nm["reason"]) == (c, "pricecharting", "no match")
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
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as c:
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


async def test_missing_targets_only_graded_stacks_without_graded_price(db):
    ids = await seed(db, "1", "2", "3")
    for cid in ids:
        await store_card_prices(db, await db.cards.find_one({"_id": cid}), await get_rates(db))
    await store_scraped_points(db, ids[1], [pt("pricecharting", "PSA9", 4000)], "2026-10-29")

    def stack(cid, grade):
        return {"stack_key": f"{cid}{grade}", "card_id": cid, "variant": None, "language": "en",
                "condition": None if grade else "NM", "quantity": 1, "created_at": datetime.now(timezone.utc),
                "grading": {"company": "PSA", "grade": grade, "cert_number": None} if grade else None}
    await db.collection_items.insert_many([stack(ids[0], 9), stack(ids[1], 9), stack(ids[2], None)])
    # [0]: slab without graded price -> needs fetch; [1]: slab priced; [2]: raw copy
    assert await pf.resolve_targets(db, missing=True) == [ids[0]]


# --- Step 1: bulk refresh ---

from app.db.models import CollectionIn   # noqa: E402
from app.services import collection as coll   # noqa: E402


async def own(db, *ids):
    for c in ids:
        await coll.add(db, CollectionIn(card_id=c, condition="NM"))


async def log_ok(db, card_id, days_ago, source="pricecharting", status="ok"):
    await db.fetch_log.insert_one({"_id": f"{card_id}|{source}", "card_id": card_id, "source": source,
                                   "status": status, "fetched_at": datetime.now(timezone.utc) - timedelta(days=days_ago)})


async def test_resolve_bulk_modes(db):
    a, b, c = await seed(db, "1", "2", "3")
    await own(db, a, b, c)
    await log_ok(db, a, 1)                 # fresh
    await log_ok(db, b, 20)                # stale
    await log_ok(db, c, 0, status="error")  # tried but never ok
    assert await pf.resolve_bulk(db, "all") == [a, b, c]
    assert await pf.resolve_bulk(db, "never") == [c]
    assert await pf.resolve_bulk(db, "stale", 7) == [c, b]          # never first, then oldest
    assert await pf.resolve_bulk(db, "stale", 30) == [c]
    item = await db.collection_items.find_one({"card_id": b})
    assert await pf.resolve_bulk(db, "stack", stack_id=str(item["_id"])) == [b]
    assert sorted(await pf.resolve_bulk(db, "valuable")) == [a, b, c]


async def test_resolve_bulk_valuable_orders_by_value(db):
    a, b = await seed(db, "1", "2")
    await db.cards.update_one({"_id": b}, {"$set": {"price_base": {"cardmarket": {"market": 99999}}}})
    await own(db, a, b)
    from app.services.collection import valuate
    vals = {v["item"]["card_id"]: v["value"] for v in await valuate(db)}
    expect = sorted([a, b], key=lambda x: -(vals[x] if vals[x] is not None else -1))
    assert await pf.resolve_bulk(db, "valuable") == expect


async def test_price_freshness_counts(db):
    a, b, c = await seed(db, "1", "2", "3")
    await own(db, a, b, c)
    await log_ok(db, a, 1)
    await log_ok(db, b, 10)
    out = await pf.price_freshness(db, 7)
    assert out == {"owned_cards": 3, "fresh": 1, "stale": 1, "never": 1, "fresh_days": 7,
                   "wishlist": {"cards": 0, "fresh": 0, "stale": 0, "never": 0}}


async def test_reasons_and_attention_summary(db):
    a, b, c = await seed(db, "1", "2", "3")
    p = FakeProvider("pricecharting", {
        a: AdapterResult("blocked", detail="cf"), b: AdapterResult("error", detail="no price table"),
        c: AdapterResult("needs_match")})
    stats = await pf.fetch_prices([b, c, a], ["pricecharting"], provider_for=providers(pricecharting=p),
                                  client=FakeClient(), mode="all")
    assert {f["card_id"]: f["reason"] for f in stats["failures"]} == {a: "blocked", b: "layout changed"}
    assert stats["needs_match_list"][0]["reason"] == "no match"
    assert pf.summary_text(stats) == "0 cards updated, 3 need attention"
    [e] = await db.alert_events.find({"type": "system"}).to_list(None)
    assert "need attention" in e["rule"] and e["key"].startswith("price_fetch_done:")


async def test_summary_notification_only_for_bulk_and_counts_cards(db):
    a, b = await seed(db, "1", "2")
    p = FakeProvider("pricecharting")
    await pf.fetch_prices([a], ["pricecharting"], provider_for=providers(pricecharting=p), client=FakeClient())
    assert await db.alert_events.count_documents({"type": "system"}) == 0
    stats = await pf.fetch_prices([a, b], ["pricecharting"], provider_for=providers(pricecharting=p),
                                  client=FakeClient(), mode="all")
    assert stats["ok_cards"] == 1 and stats["skipped_cached"] == 1      # a is cache-fresh: skipped, b fetched
    [e] = await db.alert_events.find({"type": "system"}).to_list(None)
    assert "1 cards updated" in e["rule"]


async def test_error_streak_skips_source(db):
    ids = await seed(db, "1", "2", "3", "4", "5")
    p = FakeProvider("pricecharting", default=AdapterResult("error", detail="layout"))
    stats = await pf.fetch_prices(ids, ["pricecharting"], provider_for=providers(pricecharting=p),
                                  client=FakeClient())
    assert len(p.calls) == pf.ERROR_STREAK_MAX and stats["skipped_site"] == 2
    assert stats["done"] == stats["total"] == 5


async def test_eta_from_pace_excludes_cached():
    stats = {"fetched": 0, "total": 10, "done": 0}
    assert pf._eta(stats, 5.0) is None
    stats.update(fetched=4, done=4)
    assert pf._eta(stats, 40.0) == 60            # 6 left x 10 s/fetch


async def _wait_for(pred, tries=200):
    import asyncio
    for _ in range(tries):
        if await pred():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition never met")


async def test_pause_resume_cancel_and_rerun_skips_succeeded(db, monkeypatch):
    import asyncio
    from app.services import jobs
    monkeypatch.setattr(pf, "CONTROL_POLL_S", 0.01)
    ids = await seed(db, "1", "2", "3", "4")
    gate = asyncio.Event()
    gate3 = asyncio.Event()

    class Slow(FakeProvider):
        started = 0

        async def fetch(self, card, client, known_url=None, today=None):
            Slow.started += 1
            if Slow.started == 2:
                await gate.wait()
            if Slow.started == 3:           # hold 3rd in flight so cancel lands before the 4th pair's checkpoint
                await gate3.wait()
            return await super().fetch(card, client, known_url, today)
    p = Slow("pricecharting")
    task = asyncio.create_task(pf.fetch_prices(ids, ["pricecharting"], provider_for=providers(pricecharting=p),
                                               client=FakeClient(), mode="all"))
    job_q = lambda: db.jobs.find_one({"type": "price_fetch"})   # noqa: E731

    async def calling():
        return Slow.started == 2
    await _wait_for(calling)                        # second fetch in flight (blocked on gate)
    assert await jobs.set_control(db, "price_fetch", "pause")
    gate.set()
    async def paused():
        return (await job_q())["stats"]["paused"] is True
    await _wait_for(paused)
    assert (await job_q())["status"] == "running" and len(p.calls) == 2   # parked between pairs
    assert await jobs.set_control(db, "price_fetch", "resume")
    async def third_in_flight():
        return Slow.started == 3
    await _wait_for(third_in_flight)
    await jobs.set_control(db, "price_fetch", "cancel")
    gate3.set()
    stats = await task
    job = await job_q()
    assert job["status"] == "cancelled" and stats["done"] < stats["total"] and stats["paused_s"] > 0
    done_ok = stats["ok"]
    # re-run: what succeeded is skipped, the rest fetched
    p2 = FakeProvider("pricecharting")
    s2 = await pf.fetch_prices(ids, ["pricecharting"], provider_for=providers(pricecharting=p2), client=FakeClient())
    assert s2["skipped_cached"] == done_ok and len(p2.calls) == len(ids) - done_ok


async def test_set_control_without_running_job(db):
    from app.services import jobs
    assert await jobs.set_control(db, "price_fetch", "pause") is False


async def test_api_bulk_mode_and_control(client, db, fetcher_up):
    a, b = await seed(db, "1", "2")
    await own(db, a, b)
    await log_ok(db, a, 1)
    r = await client.post("/api/admin/prices/fetch", json={"mode": "never"})
    assert r.status_code == 202 and r.json()["cards"] == 1
    assert (await client.post("/api/admin/prices/fetch", json={"mode": "stack"})).status_code == 422
    assert (await client.post("/api/admin/prices/fetch/control", json={"action": "pause"})).status_code == 404
    assert (await client.post("/api/admin/prices/fetch/control", json={"action": "nope"})).status_code == 422
    await db.jobs.insert_one({"type": "price_fetch", "status": "running", "started_at": datetime.now(timezone.utc), "stats": {}})
    assert (await client.post("/api/admin/prices/fetch/control", json={"action": "pause"})).json()["action"] == "pause"
    cur = (await client.get("/api/admin/prices/fetch/current")).json()
    assert cur["status"] == "running" and cur["control"] == "pause"


async def test_api_retry_failures(client, db, fetcher_up):
    a = (await seed(db, "1"))[0]
    assert (await client.post("/api/admin/prices/fetch/retry")).status_code == 422
    await db.jobs.insert_one({"type": "price_fetch", "status": "partial", "started_at": datetime.now(timezone.utc),
                              "stats": {"failures": [{"card_id": a, "source": "altxyz", "status": "blocked"}]}})
    r = await client.post("/api/admin/prices/fetch/retry")
    assert r.status_code == 202 and fetcher_up[-1] == ([a], ["altxyz"], False)


async def test_summary_has_price_freshness(client, db):
    [a] = await seed(db, "1")
    await own(db, a)
    await log_ok(db, a, 1)
    r = await client.get("/api/collection/summary")
    assert r.json()["prices"] == {"owned_cards": 1, "fresh": 1, "stale": 0, "never": 0, "fresh_days": 7,
                                  "wishlist": {"cards": 0, "fresh": 0, "stale": 0, "never": 0}}


async def wish(db, *ids):
    for c in ids:
        await db.wishlist.insert_one({"wish_key": f"{c}||", "card_id": c})


async def test_resolve_bulk_scopes_collection_first_and_deduped(db):
    a, b, c, d = await seed(db, "1", "2", "3", "4")
    await own(db, c, a)
    await wish(db, d, a, b)                 # a is in both
    assert await pf.resolve_bulk(db, "all") == [a, c]                              # default = collection
    assert await pf.resolve_bulk(db, "all", scope="wishlist") == [a, b, d]
    assert await pf.resolve_bulk(db, "all", scope="both") == [a, c, b, d]          # owned first, then wishlist-only
    await log_ok(db, a, 1)
    await log_ok(db, b, 20)
    assert await pf.resolve_bulk(db, "never", scope="both") == [c, d]
    assert await pf.resolve_bulk(db, "stale", 7, scope="wishlist") == [d, b]
    assert sorted(await pf.resolve_bulk(db, "valuable", scope="both")) == [a, b, c, d]


async def test_freshness_wishlist_counts(db):
    a, b, c = await seed(db, "1", "2", "3")
    await own(db, a)
    await wish(db, a, b, c)
    await log_ok(db, b, 1)
    out = await pf.price_freshness(db, 7)
    assert out["owned_cards"] == 1 and out["never"] == 1
    assert out["wishlist"] == {"cards": 2, "fresh": 1, "stale": 0, "never": 1}    # a is owned: not double counted
    assert await pf.wishlist_freshness(db, 7) == {"cards": 3, "fresh": 1, "stale": 0, "never": 2, "fresh_days": 7}


async def test_wishlist_only_run_fires_target_alert_without_snapshot(db):
    from app.db.models import WishIn
    from app.services import wishlist as wl
    from tests.test_alerts import CID, events, setup
    await setup(db, owned=False)                                   # 90.00 EUR, not owned
    await wl.add(db, WishIn(card_id=CID, target_price=8000))        # target 80.00: not hit yet
    assert await events(db) == []
    p = FakeProvider("pricecharting")                               # fetch brings a ~9.00 EUR price
    stats = await pf.fetch_prices([CID], ["pricecharting"], provider_for=providers(pricecharting=p),
                                  client=FakeClient(), mode="all", scope="wishlist")
    assert stats["ok"] == 1 and stats["scope"] == "wishlist" and stats["alerts_fired"] == 1
    assert len(await events(db)) == 1
    assert await db.collection_snapshots.count_documents({}) == 0   # nothing owned changed
    [e] = await db.alert_events.find({"type": "system"}).to_list(None)
    assert "(wishlist)" in e["rule"] and "1 alert(s) fired" in e["rule"]


async def test_owned_run_snapshots_and_alert_failure_never_fails_run(db, monkeypatch):
    [a] = await seed(db, "1")
    await own(db, a)
    p = FakeProvider("pricecharting")
    stats = await pf.fetch_prices([a], ["pricecharting"], provider_for=providers(pricecharting=p), client=FakeClient())
    assert await db.collection_snapshots.count_documents({}) == 1 and stats["ok_cards"] == 1

    async def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(pf.alerts, "evaluate", boom)
    [w] = await seed(db, "2")
    await wish(db, w)
    stats = await pf.fetch_prices([w], ["pricecharting"], provider_for=providers(pricecharting=p), client=FakeClient())
    assert stats["ok"] == 1 and (await db.jobs.find_one({"type": "price_fetch"}, sort=[("started_at", -1)]))["status"] == "ok"


async def test_stalest_owned_wishlist_flag(db):
    a, b = await seed(db, "1", "2")
    await own(db, a)
    await wish(db, b)
    assert await pf.stalest_owned(db, 10) == [a, b]
    assert await pf.stalest_owned(db, 10, wishlist=False) == [a]


async def test_api_scope_passed_and_validated(client, db, fetcher_up, monkeypatch):
    a, b = await seed(db, "1", "2")
    await own(db, a)
    await wish(db, b)
    r = await client.post("/api/admin/prices/fetch", json={"mode": "all", "scope": "both"})
    assert r.status_code == 202 and r.json()["cards"] == 2 and fetcher_up[-1][0] == [a, b]
    r = await client.post("/api/admin/prices/fetch", json={"mode": "all", "scope": "wishlist"})
    assert r.json()["cards"] == 1 and fetcher_up[-1][0] == [b]
    assert (await client.post("/api/admin/prices/fetch", json={"mode": "all", "scope": "nope"})).status_code == 422
    r = await client.get("/api/wishlist/prices")
    assert r.json() == {"cards": 1, "fresh": 0, "stale": 0, "never": 1, "fresh_days": 7}
