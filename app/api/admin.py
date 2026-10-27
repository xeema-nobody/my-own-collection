import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import get_db
from app.config import settings
from app.providers.price import registry_json
from app.services import jobs as jobs_svc
from app.services.catalog_import import import_catalog, last_failed_sets
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


async def _ensure_idle(type_: str):
    # Fast 409; the unique partial index on `jobs` is the race-free backstop.
    if await jobs_svc.is_running(get_db(), type_):
        raise HTTPException(409, f"{type_} already running")


@router.post("/catalog/import", status_code=202)
async def catalog_import(tcg: str = "pokemon", sets: list[str] | None = Query(None)):
    await _ensure_idle("catalog_import")
    _spawn(import_catalog(sets or None))
    return {"started": True}


@router.post("/catalog/import/retry-failed", status_code=202)
async def catalog_import_retry_failed():
    await _ensure_idle("catalog_import")
    failed = await last_failed_sets(get_db())
    if not failed:
        return {"started": False, "sets": []}
    _spawn(import_catalog(failed, retry=True))
    return {"started": True, "sets": failed}


@router.post("/prices/refresh", status_code=202)
async def prices_refresh(scope: str = "collection", sets: list[str] | None = Query(None)):
    await _ensure_idle("price_refresh")
    _spawn(refresh_prices(scope, sets or None))
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
            "price_sources": registry_json()}


@router.get("/price-sources")
async def price_sources():
    return registry_json()
