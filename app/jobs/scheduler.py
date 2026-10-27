from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.db.mongo import get_db
from app.services.refresh import refresh_prices

scheduler: AsyncIOScheduler | None = None


async def start_scheduler() -> AsyncIOScheduler | None:
    """Registers the daily refresh only when SCHEDULER_ENABLED; catches up a missed day on boot."""
    global scheduler
    if not settings.scheduler_enabled:
        return None
    scheduler = AsyncIOScheduler()
    scheduler.add_job(refresh_prices, CronTrigger.from_crontab(settings.price_refresh_cron),
                      id="daily_refresh", max_instances=1, coalesce=True)
    scheduler.start()
    last = await get_db().collection_snapshots.find_one(sort=[("taken_at", -1)])
    if not last or datetime.now(timezone.utc) - last["taken_at"] > timedelta(hours=24):
        scheduler.add_job(refresh_prices, id="catchup")
    return scheduler
