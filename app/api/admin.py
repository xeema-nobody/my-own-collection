import asyncio
import logging

from fastapi import APIRouter

from app.api.deps import get_db
from app.config import settings
from app.services.catalog_import import import_catalog
from app.services.refresh import refresh_prices
from app.services.snapshots import take_snapshot

router = APIRouter(prefix="/api/admin", tags=["admin"])
log = logging.getLogger(__name__)
_tasks: set[asyncio.Task] = set()


def _spawn(coro):
    # Keep a ref so the task isn't GC'd; state lives in the `jobs` collection.
    t = asyncio.create_task(coro)
    _tasks.add(t)
    t.add_done_callback(lambda t: (_tasks.discard(t), t.exception() and log.error("job failed: %s", t.exception())))


@router.post("/catalog/import", status_code=202)
async def catalog_import(tcg: str = "pokemon", set: str | None = None):
    _spawn(import_catalog(set))
    return {"started": True}


@router.post("/prices/refresh", status_code=202)
async def prices_refresh(scope: str = "collection"):
    _spawn(refresh_prices(scope))
    return {"started": True}


@router.post("/snapshot")
async def snapshot():
    d = await take_snapshot(get_db())
    d.pop("_id", None)
    return d


@router.get("/jobs")
async def jobs(limit: int = 20):
    return [{**{k: v for k, v in j.items() if k != "_id"}, "id": str(j["_id"])}
            async for j in get_db().jobs.find().sort("started_at", -1).limit(limit)]


@router.get("/status")
async def status():
    return {"base_currency": settings.base_currency, "scheduler_enabled": settings.scheduler_enabled,
            "price_refresh_cron": settings.price_refresh_cron,
            "providers": {"pokemontcg": True, "pricecharting": bool(settings.pricecharting_token),
                          "manual": True}}
