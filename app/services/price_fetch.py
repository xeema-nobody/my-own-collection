"""On-demand scraped price fetch: adapters (host fetcher) -> observations, product matches, `fetch_log`.

One `price_fetch` job at a time. Sequential card x source (the fetcher rate-limits per site anyway).
needs_match / not_found are reported, not failures; login_timeout / blocked skip that site for the run."""
import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from app.db.mongo import get_db
from app.providers.fetcher import FetcherClient, FetcherUnavailable
from app.providers.price import SCRAPED, get_provider
from app.services import alerts, jobs, matching
from app.services.collection import needs_price_card_ids, oid, valuate, valuate_wishlist
from app.services.pricing import store_scraped_points, tracked_card_ids
from app.services.sales import store_chart_seed, store_sales
from app.services.snapshots import take_snapshot

log = logging.getLogger(__name__)

CACHE_TTL = timedelta(hours=24)
STATUS_POLL_S = 2.0
CAP = 1000   # failures / needs_match entries kept in job stats
CONTROL_POLL_S = 1.0
ERROR_STREAK_MAX = 3   # consecutive adapter errors on one source -> skip it for the rest of the run
REASON = {"needs_match": "no match", "blocked": "blocked", "login_timeout": "blocked",
          "error": "layout changed", "failed": "failed"}
SOURCE_SITE = {"cardmarket_web": "cardmarket"}   # source id -> fetcher site id (default identity)


async def resolve_targets(db, cards: list[str] | None = None, sets: list[str] | None = None,
                          owned: bool = False, missing: bool = False, wishlist: bool = False) -> list[str]:
    """Card ids from explicit ids, set external ids and/or the collection; deduped, in order."""
    ids: list[str] = []
    if cards:
        ids += [c["_id"] async for c in db.cards.find({"_id": {"$in": cards}}, {"_id": 1})]
        ids.sort(key=cards.index)
    if sets:  # price scope: only tracked cards of those sets (explicit `cards` ids are a user action, kept)
        tracked = await tracked_card_ids(db)
        ids += [c["_id"] async for c in db.cards.find({"set.id": {"$in": sets}, "_id": {"$in": sorted(tracked)}}, {"_id": 1}).sort("_id", 1)]
    if owned:
        ids += sorted(await db.collection_items.distinct("card_id"))
    if missing:
        ids += await needs_price_card_ids(db)
    if wishlist:
        ids += sorted(await db.wishlist.distinct("card_id"))
    return list(dict.fromkeys(ids))


async def _last_ok(db) -> dict[str, datetime]:
    """Newest successful fetch per card (any source)."""
    last: dict[str, datetime] = {}
    async for d in db.fetch_log.find({"status": "ok"}, {"card_id": 1, "fetched_at": 1}):
        t = d["fetched_at"].replace(tzinfo=timezone.utc) if d["fetched_at"].tzinfo is None else d["fetched_at"]
        last[d["card_id"]] = max(t, last.get(d["card_id"], t))
    return last


def _bucket(card_ids, last: dict, cutoff: datetime) -> dict:
    fresh = sum(1 for c in card_ids if c in last and last[c] >= cutoff)
    never = sum(1 for c in card_ids if c not in last)
    return {"fresh": fresh, "stale": len(card_ids) - fresh - never, "never": never}


async def price_freshness(db, fresh_days: int = 7) -> dict:
    """Cards by price freshness: fresh = ok fetch within `fresh_days`, never = no ok fetch, else stale.

    Top-level keys cover owned cards; `wishlist` covers wishlisted cards not owned (no double counting)."""
    owned = await db.collection_items.distinct("card_id")
    wish = sorted(set(await db.wishlist.distinct("card_id")) - set(owned))
    last, cutoff = await _last_ok(db), datetime.now(timezone.utc) - timedelta(days=fresh_days)
    return {"owned_cards": len(owned), **_bucket(owned, last, cutoff), "fresh_days": fresh_days,
            "wishlist": {"cards": len(wish), **_bucket(wish, last, cutoff)}}


async def wishlist_freshness(db, fresh_days: int = 7) -> dict:
    """All wishlisted cards (owned or not) by price freshness, for the Wishlist page."""
    wish = sorted(await db.wishlist.distinct("card_id"))
    last, cutoff = await _last_ok(db), datetime.now(timezone.utc) - timedelta(days=fresh_days)
    return {"cards": len(wish), **_bucket(wish, last, cutoff), "fresh_days": fresh_days}


async def _order_pool(db, pool: list[str], mode: str, stale_days: int, wishlist: bool) -> list[str]:
    """Order / filter one pool of card ids by bulk mode (see resolve_bulk)."""
    pool = sorted(pool)
    if mode == "all":
        return pool
    if mode == "valuable":
        best: dict[str, int] = {}
        for v in await (valuate_wishlist if wishlist else valuate)(db):
            best[v["item"]["card_id"]] = max(best.get(v["item"]["card_id"], -1), v["value"] or -1)
        return sorted(pool, key=lambda c: -best.get(c, -1))   # sorted is stable: ties keep id order
    last = await _last_ok(db)
    if mode == "never":
        return [c for c in pool if c not in last]
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
    return sorted((c for c in pool if last.get(c, epoch) < cutoff), key=lambda c: last.get(c, epoch))


async def resolve_bulk(db, mode: str, stale_days: int = 7, stack_id: str | None = None,
                       scope: str = "collection") -> list[str]:
    """Card ids for a bulk refresh, in run order.

    scope: collection (owned), wishlist, or both (owned first, then wishlist-only cards; deduped).
    all = sorted ids; never = no ok fetch yet; stale = never or last ok older than `stale_days`
    (oldest first); valuable = highest value first, unvalued last; stack = that stack's card (scope ignored)."""
    if mode == "stack":
        it = await db.collection_items.find_one({"_id": oid(stack_id)}, {"card_id": 1}) if stack_id else None
        return [it["card_id"]] if it else []
    owned = set(await db.collection_items.distinct("card_id"))
    out: list[str] = []
    if scope in ("collection", "both"):
        out += await _order_pool(db, list(owned), mode, stale_days, False)
    if scope in ("wishlist", "both"):
        wish = set(await db.wishlist.distinct("card_id"))
        out += await _order_pool(db, list(wish - owned if scope == "both" else wish), mode, stale_days, True)
    return out


async def stalest_owned(db, limit: int, wishlist: bool = True) -> list[str]:
    """Owned (+ wishlisted unless `wishlist` is false) card ids, least recently tried first (never tried = oldest); first `limit`.

    Cards fetched today are cache-fresh and sort last, so a capped run resumes where the last stopped."""
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    last: dict[str, datetime] = {}
    async for d in db.fetch_log.find({}, {"card_id": 1, "fetched_at": 1}):
        t = d["fetched_at"].replace(tzinfo=timezone.utc) if d["fetched_at"].tzinfo is None else d["fetched_at"]
        last[d["card_id"]] = max(t, last.get(d["card_id"], t))   # last attempt on any source, any outcome
    owned = set(await db.collection_items.distinct("card_id"))
    if wishlist:
        owned |= set(await db.wishlist.distinct("card_id"))
    owned = sorted(owned)
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


def _eta(stats: dict, elapsed_s: float) -> int | None:
    """Seconds left from the observed pace of real fetches (cache / site skips cost ~nothing)."""
    if not stats["fetched"]:
        return None
    left = stats["total"] - stats["done"]
    return round(left * elapsed_s / stats["fetched"])


async def _checkpoint(db, job, stats: dict, clock=time.monotonic) -> bool:
    """Between pairs: honour pause (block, time excluded from the ETA) and cancel. True = stop the run."""
    ctl = await jobs.get_control(db, job)
    if ctl == "pause":
        t0 = clock()
        stats["paused"] = True
        await jobs.progress(db, job, stats)
        while ctl == "pause":
            await asyncio.sleep(CONTROL_POLL_S)
            ctl = await jobs.get_control(db, job)
        stats["paused_s"] += clock() - t0
        stats["paused"] = False
        await jobs.progress(db, job, stats)
    return ctl == "cancel"


def summary_text(stats: dict) -> str:
    n = stats["failed"] + stats["needs_match"]
    return (f"{stats['ok_cards']} cards updated" + (f", {n} need attention" if n else "")
            + (f", {stats['alerts_fired']} alert(s) fired" if stats.get("alerts_fired") else ""))


async def fetch_prices(card_ids: list[str], sources: list[str] | None = None, force: bool = False,
                       provider_for=get_provider, client: FetcherClient | None = None, trigger: str = "manual",
                       mode: str | None = None, scope: str | None = None) -> dict:
    db = get_db()
    client = client or FetcherClient()
    sources = [s for s in SCRAPED if not sources or s in sources]
    job = await jobs.start(db, "price_fetch", trigger)
    now = datetime.now(timezone.utc)
    stats = {"total": len(card_ids) * len(sources), "done": 0, "ok": 0, "failed": 0, "needs_match": 0,
             "not_found": 0, "sales_new": 0, "seeded": 0, "skipped_cached": 0, "skipped_site": 0, "current": None,
             "waiting_login": [], "failures": [], "needs_match_list": [], "mode": mode, "cards": len(card_ids),
             "started_at": now.isoformat(), "fetched": 0, "eta_s": None, "paused": False, "paused_s": 0.0,
             "ok_cards": 0, "scope": scope, "alerts_fired": 0}
    t_start = time.monotonic()
    owned = set(await db.collection_items.distinct("card_id"))
    owned_ok = False
    skip_sites: set[str] = set()
    streak: dict[str, int] = {}
    watcher = asyncio.create_task(_watch_login(db, job, client, stats))
    status, error = "ok", None
    try:
        aborted = cancelled = False
        for card_id in card_ids:
            if aborted or cancelled:
                break
            card = await db.cards.find_one({"_id": card_id})
            card_ok = False
            for source in sources:
                if await _checkpoint(db, job, stats):
                    cancelled = True
                    break
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
                    stats["fetched"] += 1
                    card_ok = card_ok or res == "ok"
                    streak[source] = streak.get(source, 0) + 1 if res == "error" else 0
                    if streak[source] >= ERROR_STREAK_MAX:
                        skip_sites.add(source)   # scraper likely broken or banned: stop hitting it
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
                stats["eta_s"] = _eta(stats, time.monotonic() - t_start - stats["paused_s"])
                await jobs.progress(db, job, stats)
                if aborted:
                    break
            stats["ok_cards"] += card_ok
            owned_ok = owned_ok or (card_ok and card_id in owned)
        stats["current"], stats["waiting_login"], stats["eta_s"] = None, [], None
        if stats["ok"]:
            await _after_run(db, owned_ok, now, stats)
        status = "cancelled" if cancelled else "error" if error else "partial" if stats["failed"] else "ok"
        await jobs.finish(db, job, status, stats, error)
        if mode:   # bulk run: the fetcher's notifier turns this inbox item into a macOS notification
            prefix = "Price fetch cancelled" if cancelled else "Price fetch finished"
            prefix += f" ({scope})" if scope in ("wishlist", "both") else ""
            await alerts.notify_system(db, f"price_fetch_done:{job}", f"{prefix}: {summary_text(stats)}")
    except Exception as e:  # noqa: BLE001
        await jobs.finish(db, job, "error", stats, str(e))
        raise
    finally:
        watcher.cancel()
    return stats


async def _after_run(db, owned_ok: bool, since: datetime, stats: dict):
    """Fresh prices -> collection snapshot (only if an owned card changed; it evaluates alerts itself),
    else evaluate alerts directly so wishlist target alerts fire without waiting. Never fails the run."""
    try:
        if owned_ok:
            await take_snapshot(db)
        else:
            await alerts.evaluate(db)
        stats["alerts_fired"] = await db.alert_events.count_documents({"type": "alert", "fired_at": {"$gte": since}})
    except Exception:  # noqa: BLE001
        log.exception("post-fetch snapshot/alert evaluation failed")


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
                stats["needs_match_list"].append({"card_id": card_id, "name": card.get("name"), "source": source,
                                                  "status": "needs_match", "reason": REASON["needs_match"],
                                                  "detail": res.detail})
        elif res.status == "not_found":
            stats["not_found"] += 1
        else:
            _fail(stats, card_id, source, res.status, res.detail, card.get("name"))
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
        _fail(stats, card_id, source, "failed", str(e), card.get("name"))
        return "failed"


def _fail(stats: dict, card_id: str, source: str, status: str, detail: str | None, name: str | None = None):
    stats["failed"] += 1
    if len(stats["failures"]) < CAP:
        stats["failures"].append({"card_id": card_id, "name": name, "source": source, "status": status,
                                  "reason": REASON.get(status, "failed"), "detail": detail})
