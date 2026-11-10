from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.deps import ensure_idle, get_db, spawn
from app.config import settings
from app.db.models import CollectionIn, ScanSessionIn
from app.providers.ocr import ImageError, OcrUnavailable, get_ocr
from app.security import require_laptop
from app.services import scan as svc
from app.services.refresh import price_new_tracked

router = APIRouter(prefix="/api/scan", tags=["scan"])


@router.get("/me")
async def me():
    """Phone's "am I linked" check (only reachable through the gate, which already proved the login)."""
    return {"ok": True}


@router.get("/status", dependencies=[Depends(require_laptop)])
async def status():
    """Laptop: is phone mode configured, and where does the phone go."""
    return {"enabled": bool(settings.lan_gate_secret and settings.lan_origin),
            "url": f"{settings.lan_origin}/scan" if settings.lan_origin else None,
            "login": settings.lan_login or None}


@router.post("/identify")
async def identify(request: Request, slab: bool = Query(False)):
    limit = settings.scan_max_image_mb * 1_000_000
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise HTTPException(413, "photo too large")
    raw = bytearray()  # raw image body (no multipart dependency); capped while streaming
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > limit:
            raise HTTPException(413, "photo too large")
    if not raw:
        raise HTTPException(400, "no photo received")
    try:
        return await svc.identify(get_db(), get_ocr(), bytes(raw), slab)
    except ImageError as e:
        raise HTTPException(400, str(e))
    except OcrUnavailable as e:
        raise HTTPException(503, str(e))


@router.get("/cert")
async def cert(grader: str = Query(..., min_length=2, max_length=20), cert: str = Query(..., min_length=1, max_length=20),
               refresh: bool = Query(False), grade: float | None = Query(None, ge=0, le=10),
               tier: str | None = Query(None, max_length=30)):
    """Slab cert lookup (grader's page, cached) + matching catalog cards. Never raises for a missing page. `grade`
    / `tier` (read off the label) are compared with the page for `warnings`."""
    from app.services import slab as slab_svc
    return await slab_svc.lookup(get_db(), grader, cert, refresh=refresh, label_grade=grade, label_tier=tier)


@router.get("/certs/recent", dependencies=[Depends(require_laptop)])
async def certs_recent(limit: int = Query(20, ge=1, le=100)):
    """Laptop diagnostics: the last cert lookups and how the catalog matched them."""
    from app.services import slab as slab_svc
    return await slab_svc.recent(get_db(), limit)


@router.get("/search")
async def search(q: str = Query(..., min_length=2, max_length=60), page: int = Query(1, ge=1, le=20)):
    return await svc.search(get_db(), q, page)


@router.get("/lookup")
async def lookup(number: str = Query(..., min_length=1, max_length=20), set: str | None = Query(None, max_length=60)):
    return await svc.lookup(get_db(), number, set)


@router.post("/add", status_code=201)
async def add(body: CollectionIn, session_id: str | None = Query(None, max_length=40)):
    try:
        out = await svc.add_scanned(get_db(), body, session_id)
        spawn(price_new_tracked(body.card_id))
        return out
    except svc.ScanError as e:
        raise HTTPException(e.status, str(e))


class UndoIn(BaseModel):
    event_id: str


@router.post("/undo")
async def undo(body: UndoIn):
    try:
        return await svc.undo(get_db(), body.event_id)
    except svc.ScanError as e:
        raise HTTPException(e.status, str(e))


@router.get("/session")
async def session():
    """Phone polls this: the session the laptop opened, or null."""
    return {"session": await svc.current_session(get_db())}


@router.post("/sessions", status_code=201, dependencies=[Depends(require_laptop)])
async def start_session(body: ScanSessionIn | None = None):
    return await svc.start_session(get_db(), (body or ScanSessionIn()).mode)


@router.delete("/sessions/{session_id}", status_code=204, dependencies=[Depends(require_laptop)])
async def close_session(session_id: str):
    if not await svc.close_session(get_db(), session_id):
        raise HTTPException(404, "session not found")


@router.get("/events", dependencies=[Depends(require_laptop)])
async def events(after: str | None = None, session_id: str | None = None):
    return await svc.events_after(get_db(), after, session_id)


@router.get("/ja/suggest")
async def ja_suggest(code: str | None = Query(None, max_length=20), total: int | None = Query(None, ge=1, le=1000),
                     set_name: str | None = Query(None, max_length=80), q: str | None = Query(None, max_length=40)):
    """Japanese sets worth importing for a scan / slab with no match (live set list, cached; [] when TCGdex is down)."""
    from app.services import ja_suggest as ja
    try:
        return {"sets": await ja.suggest(code, total, set_name, q)}
    except Exception:  # noqa: BLE001 - upstream down: the prompt just offers nothing
        return {"sets": []}


@router.post("/ja/import", status_code=202)
async def ja_import(set: str = Query(..., min_length=1, max_length=20)):
    """Import ONE Japanese set into the catalog (never the collection). The id must be in TCGdex's live ja list."""
    from app.services import catalog_ja, ja_suggest as ja
    try:
        found = await ja.find_set(set)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"catalog provider unavailable: {e}") from None
    if not found:
        raise HTTPException(404, "unknown Japanese set")
    await ensure_idle("catalog_import")
    ja.reset_cache()   # held counts change as the job runs
    spawn(catalog_ja.import_ja_sets([set], trigger="scan"))
    return {"started": True, "set": set}


@router.get("/ja/import")
async def ja_import_status():
    from app.services import ja_suggest as ja
    return await ja.import_status(get_db())
