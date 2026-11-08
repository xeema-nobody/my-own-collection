from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.deps import get_db
from app.config import settings
from app.db.models import CollectionIn, ScanSessionIn
from app.providers.ocr import ImageError, OcrUnavailable, get_ocr
from app.security import require_laptop
from app.services import scan as svc

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


@router.get("/search")
async def search(q: str = Query(..., min_length=2, max_length=60), page: int = Query(1, ge=1, le=20)):
    return await svc.search(get_db(), q, page)


@router.get("/lookup")
async def lookup(number: str = Query(..., min_length=1, max_length=20), set: str | None = Query(None, max_length=60)):
    return await svc.lookup(get_db(), number, set)


@router.post("/add", status_code=201)
async def add(body: CollectionIn, session_id: str | None = Query(None, max_length=40)):
    try:
        return await svc.add_scanned(get_db(), body, session_id)
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
