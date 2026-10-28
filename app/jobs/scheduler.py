import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.db.mongo import get_db
from app.providers.fetcher import FetcherClient, FetcherUnavailable
from app.services import alerts, jobs
from app.services.catalog_import import import_catalog
from app.services.price_fetch import fetch_prices, stalest_owned
from app.services.refresh import refresh_prices
from app.services.snapshots import take_snapshot

log = logging.getLogger(__name__)

scheduler: AsyncIOScheduler | None = None
DAY, WEEK = timedelta(hours=24), timedelta(days=7)


async def _refresh(trigger: str):
    await refresh_prices("collection", trigger=trigger)


async def _fetch(trigger: str):
    """Scraped prices for the stalest owned cards. Unattended: sites needing login are skipped."""
    db = get_db()
    client = FetcherClient(unattended=True)
    try:
        await client.status()
    except FetcherUnavailable as e:
        await jobs.record_skipped(db, "price_fetch", trigger, str(e))
        await alerts.notify_system(db, f"fetch_skipped:{datetime.now(timezone.utc):%Y-%m-%d}",
                                   f"Scheduled fetch skipped: fetcher not running ({e})")
        return
    cards = await stalest_owned(db, settings.scheduler_fetch_cap)
    if cards:
        await fetch_prices(cards, client=client, trigger=trigger)


async def _snapshot(trigger: str):
    await take_snapshot(get_db())


async def _catalog(trigger: str):
    await import_catalog(trigger=trigger)


async def _prune(trigger: str):
    n = await alerts.prune_events(get_db())
    log.info("scheduler: pruned %d read alert events", n)


# id -> (runner, cron setting, job type for catch-up age check, max age)
TASKS: dict[str, tuple[Callable[[str], Awaitable[None]], str, str | None, timedelta | None]] = {
    "daily_refresh": (_refresh, "price_refresh_cron", "price_refresh", DAY),
    "daily_fetch": (_fetch, "price_fetch_cron", "price_fetch", DAY),
    "daily_snapshot": (_snapshot, "snapshot_cron", None, DAY),   # None: age from collection_snapshots
    "weekly_catalog": (_catalog, "catalog_import_cron", "catalog_import", WEEK),
    "daily_prune": (_prune, "alert_prune_cron", None, None),   # max age None: housekeeping, no catch-up
}


async def run_task(name: str, trigger: str = "scheduler", runners: dict | None = None) -> bool:
    """One task, fully isolated: a failure or a busy job type never reaches the scheduler or other tasks."""
    fn = (runners or {}).get(name) or TASKS[name][0]
    try:
        await fn(trigger)
        return True
    except jobs.JobRunning:
        log.info("scheduler: %s skipped, already running", name)
    except Exception:  # noqa: BLE001
        log.exception("scheduler: %s failed", name)
    return False


async def _last_run(db, name: str) -> datetime | None:
    type_ = TASKS[name][2]
    if type_:
        return await jobs.last_success(db, type_)
    last = await db.collection_snapshots.find_one(sort=[("taken_at", -1)])
    return last["taken_at"] if last else None


async def overdue(db, now: datetime) -> list[str]:
    """Tasks whose last success is older than their max age (or missing), in TASKS order."""
    out = []
    for name, (_, _, _, max_age) in TASKS.items():
        if max_age is None:
            continue
        last = await _last_run(db, name)
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if last is not None and now - last <= max_age:
            continue
        if name == "weekly_catalog" and not await db.sets.find_one({}, {"_id": 1}):
            continue   # first import is a deliberate act from Settings
        out.append(name)
    return out


async def catch_up(db, now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                   runners: dict | None = None) -> list[str]:
    """Runs each overdue task once, sequentially. Returns the names attempted."""
    todo = await overdue(db, now())
    for name in todo:
        await run_task(name, "catchup", runners)
    return todo


def build_scheduler() -> AsyncIOScheduler:
    s = AsyncIOScheduler()
    for name, (_, cron_attr, _, _) in TASKS.items():
        s.add_job(run_task, CronTrigger.from_crontab(getattr(settings, cron_attr)), args=[name],
                  id=name, max_instances=1, coalesce=True)
    return s


def next_runs() -> list[dict]:
    if not scheduler:
        return []
    return [{"id": j.id, "next_run": j.next_run_time.isoformat() if j.next_run_time else None}
            for j in scheduler.get_jobs()]


async def start_scheduler() -> AsyncIOScheduler | None:
    """Registers the tasks only when SCHEDULER_ENABLED; catches up missed ones in the background on boot."""
    global scheduler
    if not settings.scheduler_enabled:
        return None
    scheduler = build_scheduler()
    scheduler.start()
    asyncio.create_task(catch_up(get_db()))   # not awaited: boot must not wait for fetches
    return scheduler
