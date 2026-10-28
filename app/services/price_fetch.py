"""On-demand scraped price fetch: adapters (host fetcher) -> observations, product matches, `fetch_log`.

One `price_fetch` job at a time. Sequential card x source (the fetcher rate-limits per site anyway).
needs_match / not_found are reported, not failures; login_timeout / blocked skip that site for the run."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.db.mongo import get_db
from app.providers.fetcher import FetcherClient, FetcherUnavailable
from app.providers.price import SCRAPED, get_provider
from app.services import alerts, jobs, matching
from app.services.pricing import store_scraped_points
from app.services.sales import store_chart_seed, store_sales
from app.services.snapshots import take_snapshot

log = logging.getLogger(__name__)

CACHE_TTL = timedelta(hours=24)
STATUS_POLL_S = 2.0
CAP = 50   # failures / needs_match entries kept in job stats
SOURCE_SITE = {"cardmarket_web": "cardmarket"}   # source id -> fetcher site id (default identity)


async def resolve_targets(db, cards: list[str] | None = None, sets: list[str] | None = None,
                          owned: bool = False) -> list[str]:
    """Card ids from explicit ids, set external ids and/or the collection; deduped, in order."""
    ids: list[str] = []
    if cards:
        ids += [c["_id"] async for c in db.cards.find({"_id": {"$in": cards}}, {"_id": 1})]
        ids.sort(key=cards.index)
    if sets:
        ids += [c["_id"] async for c in db.cards.find({"set.id": {"$in": sets}}, {"_id": 1}).sort("_id", 1)]
    if owned:
        ids += sorted(await db.collection_items.distinct("card_id"))
    return list(dict.fromkeys(ids))


async def stalest_owned(db, limit: int) -> list[str]:
    """Owned card ids, least recently tried first (never tried = oldest); first `limit`.

    Cards fetched today are cache-fresh and sort last, so a capped run resumes where the last stopped."""
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    last: dict[str, datetime] = {}
    async for d in db.fetch_log.find({}, {"card_id": 1, "fetched_at": 1}):
        t = d["fetched_at"].replace(tzinfo=timezone.utc) if d["fetched_at"].tzinfo is None else d["fetched_at"]
        last[d["card_id"]] = max(t, last.get(d["card_id"], t))   # last attempt on any source, any outcome
    owned = sorted(await db.collection_items.distinct("card_id"))
    owned.sort(key=lambda c: last.get(c, epoch))
    return owned[:limit]


async def fetch_status(db, card_id: str) -> dict[str, dict | None]:
    """Last `fetch_log` entry per scraped source; None when never fetched."""
    rows = {d["source"]: d async for d in db.fetch_log.find({"card_id": card_id})}
    return {s: ({k: rows[s].get(k) for k in ("status", "detail", "url", "fetched_at")} if s in rows else None)
            for s in SCRAPED}


async def _fresh(db, card_id: str, source: str) -> bool:
    d = await db.fetch_log.find_one({"_id": f"{card_id}|{source}"}, {"status": 1, "fetched_at": 1})
    if not d or d.get("status") != "ok" or not d.get("fetched_at"):
        return False
    return datetime.now(timezone.utc) - d["fetched_at"].replace(tzinfo=timezone.utc) < CACHE_TTL


async def _watch_login(db, job_id, client, stats: dict):
    """Surface 'waiting for login' while an adapter blocks on the fetcher."""
    site_src = {SOURCE_SITE.get(s, s): s for s in SCRAPED}
    while True:
        await asyncio.sleep(STATUS_POLL_S)
        try:
            sites = (await client.status()).get("sites", {})
        except FetcherUnavailable:
            continue
        waiting = sorted(site_src[s] for s, st in sites.items()
                         if s in site_src and str(st).startswith("waiting_login"))
        if waiting != stats["waiting_login"]:
            stats["waiting_login"] = waiting
            await jobs.progress(db, job_id, stats)


async def fetch_prices(card_ids: list[str], sources: list[str] | None = None, force: bool = False,
                       provider_for=get_provider, client: FetcherClient | None = None, trigger: str = "manual") -> dict:
    db = get_db()
    client = client or FetcherClient()
    sources = [s for s in SCRAPED if not sources or s in sources]
    job = await jobs.start(db, "price_fetch", trigger)
    stats = {"total": len(card_ids) * len(sources), "done": 0, "ok": 0, "failed": 0, "needs_match": 0,
             "not_found": 0, "sales_new": 0, "seeded": 0, "skipped_cached": 0, "skipped_site": 0, "current": None,
             "waiting_login": [], "failures": [], "needs_match_list": []}
    skip_sites: set[str] = set()
    watcher = asyncio.create_task(_watch_login(db, job, client, stats))
    status, error = "ok", None
    try:
        aborted = False
        for card_id in card_ids:
            if aborted:
                break
            card = await db.cards.find_one({"_id": card_id})
            for source in sources:
                if card is None:
                    _fail(stats, card_id, source, "failed", "card not found")
                elif source in skip_sites:
                    stats["skipped_site"] += 1
                elif not force and await _fresh(db, card_id, source):
                    stats["skipped_cached"] += 1
                else:
                    stats["current"] = {"card_id": card_id, "source": source}
                    await jobs.progress(db, job, stats)
                    res = await _fetch_one(db, client, provider_for(source), card, source, stats)
                    if res in ("login_timeout", "blocked"):
                        skip_sites.add(source)
                        if trigger != "manual":
                            await alerts.notify_system(
                                db, f"login_needed:{source}:{datetime.now(timezone.utc):%Y-%m-%d}",
                                f"Scheduled fetch skipped {source}: login or challenge needed "
                                f"(log in via Settings > Fetch)")
                    elif res == "unreachable":
                        error, aborted = "fetcher unreachable", True
                        stats["skipped_site"] += stats["total"] - stats["done"] - 1
                        stats["done"] = stats["total"] - 1   # +1 below
                stats["done"] += 1
                await jobs.progress(db, job, stats)
                if aborted:
                    break
        stats["current"], stats["waiting_login"] = None, []
        if stats["ok"]:
            await take_snapshot(db)
        status = "error" if error else "partial" if stats["failed"] else "ok"
        await jobs.finish(db, job, status, stats, error)
    except Exception as e:  # noqa: BLE001
        await jobs.finish(db, job, "error", stats, str(e))
        raise
    finally:
        watcher.cancel()
    return stats


async def _fetch_one(db, client, provider, card: dict, source: str, stats: dict) -> str:
    """Run one adapter, persist + tally. Returns the adapter status, 'failed' or 'unreachable'."""
    card_id = card["_id"]
    try:
        known = await matching.known_url(db, card_id, source) if source in matching.MATCHABLE else None
        res = await provider.fetch(card, client, known)
        await matching.record_result(db, card_id, source, res)
        if res.status == "ok":
            await store_scraped_points(db, card_id, res.points)
            stats["sales_new"] += await store_sales(db, card_id, res.sales)
            stats["seeded"] += await store_chart_seed(db, card_id, source, res.chart)
            stats["ok"] += 1
        elif res.status == "needs_match":
            stats["needs_match"] += 1
            if len(stats["needs_match_list"]) < CAP:
                stats["needs_match_list"].append({"card_id": card_id, "source": source})
        elif res.status == "not_found":
            stats["not_found"] += 1
        else:
            _fail(stats, card_id, source, res.status, res.detail)
        await db.fetch_log.update_one(
            {"_id": f"{card_id}|{source}"},
            {"$set": {"card_id": card_id, "source": source, "status": res.status, "detail": res.detail,
                      "url": res.url, "fetched_at": datetime.now(timezone.utc)}}, upsert=True)
        if res.status == "error":
            try:
                await client.status()
            except FetcherUnavailable:
                return "unreachable"
        return res.status
    except Exception as e:  # noqa: BLE001 - one pair failing must not abort the rest
        log.warning("fetch %s %s failed: %s", card_id, source, e)
        _fail(stats, card_id, source, "failed", str(e))
        return "failed"


def _fail(stats: dict, card_id: str, source: str, status: str, detail: str | None):
    stats["failed"] += 1
    if len(stats["failures"]) < CAP:
        stats["failures"].append({"card_id": card_id, "source": source, "status": status, "detail": detail})
