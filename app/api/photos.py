from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel

from app.api.deps import get_db
from app.config import settings
from app.services import photos as svc

router = APIRouter(tags=["photos"])


async def _body(request: Request) -> bytes:
    limit = settings.scan_max_image_mb * 1_000_000
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise HTTPException(413, "photo too large")
    raw = bytearray()
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > limit:
            raise HTTPException(413, "photo too large")
    if not raw:
        raise HTTPException(400, "no photo received")
    return bytes(raw)


def _wrap(e: svc.PhotoError):
    return HTTPException(e.status, str(e))


@router.get("/api/collection/{stack_id}/photos")
async def list_photos(stack_id: str):
    return await svc.list_for_stack(get_db(), stack_id)


@router.post("/api/collection/{stack_id}/photos", status_code=201)
async def add_photo(stack_id: str, request: Request, kind: str = Query("other", max_length=20)):
    raw = await _body(request)
    try:
        return await svc.add(get_db(), stack_id, raw, kind)
    except svc.PhotoError as e:
        raise _wrap(e)


@router.post("/api/scan/photo", status_code=201)
async def scan_photo(request: Request, stack_id: str = Query(..., max_length=40),
                     kind: str = Query("other", max_length=20)):
    """Phone: keep the scanned photo (or a back / corner shot) with the stack it just added."""
    db = get_db()
    if not await svc.scan_stack_ok(db, stack_id):
        raise HTTPException(403, "photos can only be added to a card you just scanned")
    raw = await _body(request)
    try:
        return await svc.add(db, stack_id, raw, kind)
    except svc.PhotoError as e:
        raise _wrap(e)


@router.get("/api/photos/stats")
async def photo_stats():
    return await svc.stats(get_db())


@router.get("/api/photos/{photo_id}")
async def get_photo(photo_id: str, size: str = Query("full", pattern="^(full|thumb)$")):
    try:
        data = await svc.image(get_db(), photo_id, size)
    except svc.PhotoError as e:
        raise _wrap(e)
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


class PhotoPatch(BaseModel):
    kind: str | None = None
    cover: bool | None = None
    position: int | None = None


@router.patch("/api/photos/{photo_id}")
async def patch_photo(photo_id: str, body: PhotoPatch):
    try:
        return await svc.update(get_db(), photo_id, body.kind, body.cover, body.position)
    except svc.PhotoError as e:
        raise _wrap(e)


@router.delete("/api/photos/{photo_id}", status_code=204)
async def delete_photo(photo_id: str):
    try:
        await svc.delete(get_db(), photo_id)
    except svc.PhotoError as e:
        raise _wrap(e)
