from fastapi import APIRouter, HTTPException, Query

from app.api.deps import ensure_idle, get_db, spawn
from app.config import settings
from app.db.models import FetchIn
from app.providers.fetcher import FetcherClient, FetcherUnavailable
from app.providers.price import registry_json
from app.services.catalog_import import import_catalog, last_failed_sets
from app.services.price_fetch import fetch_prices, resolve_targets
from app.services.refresh import refresh_prices
from app.services.snapshots import take_snapshot

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/catalog/import", status_code=202)
async def catalog_import(tcg: str = "pokemon", sets: list[str] | None = Query(None)):
    await ensure_idle("catalog_import")
    spawn(import_catalog(sets or None))
    return {"started": True}


@router.post("/catalog/import/retry-failed", status_code=202)
async def catalog_import_retry_failed():
    await ensure_idle("catalog_import")
    failed = await last_failed_sets(get_db())
    if not failed:
        return {"started": False, "sets": []}
    spawn(import_catalog(failed, retry=True))
    return {"started": True, "sets": failed}


@router.post("/prices/refresh", status_code=202)
async def prices_refresh(scope: str = "collection", sets: list[str] | None = Query(None)):
    await ensure_idle("price_refresh")
    spawn(refresh_prices(scope, sets or None))
    return {"started": True}


@router.post("/prices/fetch", status_code=202)
async def prices_fetch(body: FetchIn):
    """On-demand scraped price fetch (host fetcher) for cards / sets / owned."""
    await ensure_idle("price_fetch")
    try:
        await FetcherClient().status()
    except FetcherUnavailable as e:
        raise HTTPException(503, str(e)) from None
    cards = await resolve_targets(get_db(), body.cards, body.sets, body.owned)
    if not cards:
        raise HTTPException(422, "no cards match the given targets")
    spawn(fetch_prices(cards, body.sources, body.force))
    return {"started": True, "cards": len(cards)}


@router.get("/fetcher-status")
async def fetcher_status():
    """Indicator for the UI: an unreachable fetcher is a state, not an error."""
    try:
        return {"up": True, **await FetcherClient().status()}
    except FetcherUnavailable as e:
        return {"up": False, "detail": str(e)}


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
