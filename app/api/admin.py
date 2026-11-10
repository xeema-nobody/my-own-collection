from fastapi import APIRouter, HTTPException, Query

from app.api.deps import ensure_idle, get_db, spawn
from app.config import settings
from app.jobs import scheduler as sched
from app.db.models import FetchControlIn, FetchIn
from app.providers.fetcher import FetcherClient, FetcherUnavailable
from app.providers.price import registry_json
from app.services.catalog_import import import_catalog, incomplete_sets
from app.services import catalog_audit, catalog_images, catalog_ja, jobs as jobs_svc
from app.services.price_fetch import fetch_prices, resolve_bulk, resolve_targets
from app.services.refresh import SCOPES, refresh_prices
from app.services.snapshots import take_snapshot

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/catalog/audit")
async def catalog_audit_route():
    """Provider's live set list vs the database (one upstream call, no card download)."""
    try:
        return await catalog_audit.audit(get_db())
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"catalog provider unavailable: {e}") from None


@router.post("/catalog/import", status_code=202)
async def catalog_import(tcg: str = "pokemon", sets: list[str] | None = Query(None)):
    await ensure_idle("catalog_import")
    spawn(import_catalog(sets or None))
    return {"started": True}


@router.get("/catalog/ja/sets")
async def catalog_ja_sets():
    """Japanese sets TCGdex lists (one live request) with how many cards we hold."""
    try:
        return await catalog_ja.list_ja_sets()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"catalog provider unavailable: {e}") from None


@router.post("/catalog/ja/import", status_code=202)
async def catalog_ja_import(sets: list[str] = Query(...)):
    await ensure_idle("catalog_import")
    spawn(catalog_ja.import_ja_sets(sets))
    return {"started": True, "sets": sets}


@router.get("/catalog/images/status")
async def catalog_images_status():
    return await catalog_images.status()


@router.post("/catalog/images/repoint", status_code=202)
async def catalog_images_repoint():
    """Move stored card images from images.pokemontcg.io to TCGdex assets (reversible, idempotent)."""
    await ensure_idle("catalog_images")
    spawn(catalog_images.repoint_images())
    return {"started": True}


@router.post("/catalog/images/restore")
async def catalog_images_restore():
    await ensure_idle("catalog_images")
    return {"restored": await catalog_images.restore_images()}


@router.post("/catalog/import/retry-incomplete", status_code=202)
async def catalog_import_retry_incomplete():
    await ensure_idle("catalog_import")
    todo = await incomplete_sets(get_db())
    if not todo:
        return {"started": False, "sets": []}
    spawn(import_catalog(todo, retry=True))
    return {"started": True, "sets": todo}


@router.post("/prices/refresh", status_code=202)
async def prices_refresh(scope: str = "tracked", sets: list[str] | None = Query(None)):
    if scope not in SCOPES:
        raise HTTPException(422, f"scope must be one of {', '.join(SCOPES)} (prices are stored for tracked cards only)")
    await ensure_idle("price_refresh")
    spawn(refresh_prices(scope, sets or None))
    return {"started": True}


@router.post("/prices/fetch", status_code=202)
async def prices_fetch(body: FetchIn):
    """On-demand scraped price fetch (host fetcher) for cards / sets / owned, or a bulk `mode` over the collection."""
    await ensure_idle("price_fetch")
    await _need_fetcher()
    db = get_db()
    cards = await resolve_targets(db, body.cards, body.sets, body.owned, body.missing, body.wishlist)
    if body.mode:
        cards = list(dict.fromkeys(cards + await resolve_bulk(db, body.mode, body.stale_days, body.stack_id, body.scope)))
    if not cards:
        raise HTTPException(422, "no cards match the given targets")
    spawn(fetch_prices(cards, body.sources, body.force, mode=body.mode, scope=body.scope if body.mode else None))
    return {"started": True, "cards": len(cards)}


@router.get("/prices/fetch/current")
async def prices_fetch_current():
    """Running (else latest) price_fetch job, so any page can show progress after a reload."""
    return await jobs_svc.current(get_db(), "price_fetch")


@router.post("/prices/fetch/control")
async def prices_fetch_control(body: FetchControlIn):
    if not await jobs_svc.set_control(get_db(), "price_fetch", body.action):
        raise HTTPException(404, "no price fetch running")
    return {"ok": True, "action": body.action}


@router.post("/prices/fetch/retry", status_code=202)
async def prices_fetch_retry():
    """Re-run the last fetch's failures (not 'no match': those need a manual match first)."""
    await ensure_idle("price_fetch")
    await _need_fetcher()
    last = await jobs_svc.current(get_db(), "price_fetch")
    failed = [f for f in (last or {}).get("stats", {}).get("failures", [])]
    cards = list(dict.fromkeys(f["card_id"] for f in failed))
    if not cards:
        raise HTTPException(422, "nothing to retry")
    # Pairs that already succeeded are cache-fresh and skipped; only failed ones hit the network again.
    spawn(fetch_prices(cards, sorted({f["source"] for f in failed}), False, mode="retry"))
    return {"started": True, "cards": len(cards)}


async def _need_fetcher():
    try:
        await FetcherClient().status()
    except FetcherUnavailable as e:
        raise HTTPException(503, str(e)) from None


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
async def jobs(limit: int = Query(20, ge=1, le=200)):
    return [{**{k: v for k, v in j.items() if k != "_id"}, "id": str(j["_id"])}
            async for j in get_db().jobs.find().sort("started_at", -1).limit(limit)]


@router.get("/status")
async def status():
    return {"base_currency": settings.base_currency, "scheduler_enabled": settings.scheduler_enabled,
            "price_refresh_cron": settings.price_refresh_cron,
            "scheduler": {"enabled": settings.scheduler_enabled, "jobs": sched.next_runs()},
            "price_sources": registry_json()}


@router.get("/price-sources")
async def price_sources():
    return registry_json()
