"""Photos on a collection stack (roadmap 6a). Compressed JPEG + thumbnail kept in Mongo (`photos`), so mongodump
covers them. A photo belongs to the stack (copies are only a counter). EXIF is applied then dropped (no GPS)."""
import asyncio
import io
from datetime import datetime, timedelta, timezone

from bson import Binary, ObjectId
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import settings

KINDS = ("front", "back", "corner", "surface", "slab_front", "slab_back", "other")
Image.MAX_IMAGE_PIXELS = 40_000_000


class PhotoError(Exception):
    def __init__(self, status: int, msg: str):
        super().__init__(msg)
        self.status = status


def _jpeg(im: Image.Image, side: int, quality: int) -> tuple[bytes, int, int]:
    im = im.copy()
    im.thumbnail((side, side), Image.LANCZOS)  # only shrinks
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue(), im.width, im.height


def compress(raw: bytes) -> tuple[bytes, bytes, int, int]:
    """(full jpeg, thumb jpeg, width, height). Raises PhotoError for anything that is not a JPEG/PNG/WebP image."""
    try:
        im = Image.open(io.BytesIO(raw))
        if im.format not in ("JPEG", "PNG", "WEBP", "MPO"):
            raise PhotoError(400, "unsupported image type (use JPEG, PNG or WebP)")
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", im.size, (255, 255, 255))
            im = im.convert("RGBA")
            bg.paste(im, mask=im.getchannel("A"))
            im = bg
        else:
            im = im.convert("RGB")
    except PhotoError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError):
        raise PhotoError(400, "not a readable image")
    full, w, h = _jpeg(im, settings.photo_max_side, settings.photo_quality)
    thumb, _, _ = _jpeg(im, settings.photo_thumb_side, 75)
    return full, thumb, w, h


def _oid(value: str, what: str = "photo") -> ObjectId:
    try:
        return ObjectId(value)
    except Exception:
        raise PhotoError(404, f"{what} not found")


def _meta(d: dict) -> dict:
    return {"id": str(d["_id"]), "stack_id": d["stack_id"], "kind": d["kind"], "cover": bool(d.get("cover")),
            "order": d["order"], "w": d["w"], "h": d["h"], "bytes": d["bytes"], "created_at": d["created_at"]}


_LIGHT = {"data": 0, "thumb": 0}


async def list_for_stack(db, stack_id: str) -> list[dict]:
    cur = db.photos.find({"stack_id": stack_id}, _LIGHT).sort("order", 1)
    return [_meta(d) async for d in cur]


async def add(db, stack_id: str, raw: bytes, kind: str = "other") -> dict:
    if kind not in KINDS:
        raise PhotoError(422, f"kind must be one of {', '.join(KINDS)}")
    if not await db.collection_items.find_one({"_id": _oid(stack_id, "stack")}, {"_id": 1}):
        raise PhotoError(404, "stack not found")
    if await db.photos.count_documents({"stack_id": stack_id}) >= settings.photo_max_per_stack:
        raise PhotoError(409, f"at most {settings.photo_max_per_stack} photos per card")
    full, thumb, w, h = await asyncio.to_thread(compress, raw)
    last = await db.photos.find_one({"stack_id": stack_id}, {"order": 1}, sort=[("order", -1)])
    first = last is None
    doc = {"stack_id": stack_id, "kind": kind, "cover": first, "order": 0 if first else last["order"] + 1,
           "data": Binary(full), "thumb": Binary(thumb), "w": w, "h": h, "bytes": len(full) + len(thumb),
           "created_at": datetime.now(timezone.utc)}
    res = await db.photos.insert_one(doc)
    return _meta({**doc, "_id": res.inserted_id})


async def image(db, photo_id: str, size: str = "full") -> bytes:
    d = await db.photos.find_one({"_id": _oid(photo_id)}, {"thumb": 1} if size == "thumb" else {"data": 1})
    if not d:
        raise PhotoError(404, "photo not found")
    return bytes(d["thumb" if size == "thumb" else "data"])


async def update(db, photo_id: str, kind: str | None = None, cover: bool | None = None,
                 position: int | None = None) -> dict:
    oid = _oid(photo_id)
    d = await db.photos.find_one({"_id": oid}, _LIGHT)
    if not d:
        raise PhotoError(404, "photo not found")
    if kind is not None:
        if kind not in KINDS:
            raise PhotoError(422, f"kind must be one of {', '.join(KINDS)}")
        await db.photos.update_one({"_id": oid}, {"$set": {"kind": kind}})
    if cover:
        await db.photos.update_many({"stack_id": d["stack_id"]}, {"$set": {"cover": False}})
        await db.photos.update_one({"_id": oid}, {"$set": {"cover": True}})
    elif cover is False and d.get("cover"):
        raise PhotoError(422, "pick another photo as cover instead")
    if position is not None:
        ids = [x["_id"] async for x in db.photos.find({"stack_id": d["stack_id"]}, {"_id": 1}).sort("order", 1)]
        ids.remove(oid)
        ids.insert(max(0, min(position, len(ids))), oid)
        for i, pid in enumerate(ids):
            await db.photos.update_one({"_id": pid}, {"$set": {"order": i}})
    return _meta(await db.photos.find_one({"_id": oid}, _LIGHT))


async def delete(db, photo_id: str) -> None:
    oid = _oid(photo_id)
    d = await db.photos.find_one({"_id": oid}, _LIGHT)
    if not d:
        raise PhotoError(404, "photo not found")
    await db.photos.delete_one({"_id": oid})
    if d.get("cover"):  # the first remaining photo takes over
        nxt = await db.photos.find_one({"stack_id": d["stack_id"]}, {"_id": 1}, sort=[("order", 1)])
        if nxt:
            await db.photos.update_one({"_id": nxt["_id"]}, {"$set": {"cover": True}})


async def delete_for_stack(db, stack_id: str) -> int:
    return (await db.photos.delete_many({"stack_id": stack_id})).deleted_count


async def counts(db, stack_ids: list[str]) -> dict[str, dict]:
    """{stack_id: {count, cover}} for the stacks that have photos (one aggregate)."""
    if not stack_ids:
        return {}
    out: dict[str, dict] = {}
    cur = db.photos.aggregate([
        {"$match": {"stack_id": {"$in": stack_ids}}},
        {"$group": {"_id": "$stack_id", "count": {"$sum": 1},
                    "cover": {"$max": {"$cond": ["$cover", {"$toString": "$_id"}, None]}}}}])
    async for r in cur:
        out[r["_id"]] = {"count": r["count"], "cover": r["cover"]}
    return out


async def stats(db) -> dict:
    cur = db.photos.aggregate([{"$group": {"_id": None, "count": {"$sum": 1}, "bytes": {"$sum": "$bytes"}}}])
    r = await cur.to_list(1)
    return {"count": r[0]["count"], "bytes": r[0]["bytes"]} if r else {"count": 0, "bytes": 0}


async def scan_stack_ok(db, stack_id: str) -> bool:
    """The phone may add photos only to a stack it just scanned (recent, not undone add event)."""
    since = datetime.now(timezone.utc) - timedelta(days=settings.scan_event_keep_days)
    return bool(await db.scan_events.find_one(
        {"stack_id": stack_id, "kind": {"$in": ["add", None]}, "undone": {"$ne": True}, "at": {"$gte": since}}, {"_id": 1}))
