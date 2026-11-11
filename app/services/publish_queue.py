"""Assisted Vinted publish queue (roadmap 6e). The user confirms each item in the app; confirmed items wait in
`publish_queue` until a Claude session with Chrome claims one, fills Vinted's form, uploads and reports back.
The backend never drives the browser. One active (confirmed / publishing) entry per stack. Money is integer cents."""
import asyncio
import shutil
from datetime import datetime, timezone
from pathlib import Path

from bson import ObjectId

from app.config import settings
from app.db.models import PublishConfirmIn, PublishResultIn, StackSaleIn
from app.services import photos as photos_svc, sale, valuation_cache

ACTIVE = ("confirmed", "publishing")
STATES = ("confirmed", "publishing", "published", "failed", "cancelled")
VINTED_MAX_PHOTOS = 20
VINTED_BASE = "https://www.vinted.nl"


class QueueError(Exception):
    def __init__(self, status: int, msg: str):
        super().__init__(msg)
        self.status = status


def _oid(v: str) -> ObjectId:
    try:
        return ObjectId(v)
    except Exception:
        raise QueueError(404, "queue item not found")


def _view(d: dict) -> dict:
    out = {**d, "id": str(d.pop("_id"))} if "_id" in d else dict(d)
    out.pop("_id", None)
    return out


def _dir(qid: str) -> Path:
    return Path(settings.publish_dir) / qid


def _clean(qid: str) -> None:
    shutil.rmtree(_dir(qid), ignore_errors=True)


def vinted_link(item: dict) -> str | None:
    for l in (item.get("sale") or {}).get("listings") or []:
        if l.get("platform") == "vinted" and l.get("url"):
            return l["url"]
    return None


def _edit_url(link: str) -> str:
    """Vinted item page -> its edit page. https://www.vinted.nl/items/123-name -> .../items/123/edit (id only)."""
    tail = link.rstrip("/").split("/items/")[-1].split("?")[0]
    return f"{link.split('/items/')[0]}/items/{tail.split('-')[0]}/edit" if "/items/" in link else link


async def confirm(db, body: PublishConfirmIn) -> dict:
    """Queue the confirmed items. A stack that is already queued (confirmed / publishing) is refused, not duplicated."""
    results = []
    for it in body.items:
        try:
            oid = ObjectId(it.item_id)
        except Exception:
            results.append({"item_id": it.item_id, "ok": False, "error": "stack not found"})
            continue
        stack = await db.collection_items.find_one({"_id": oid})
        if not stack:
            results.append({"item_id": it.item_id, "ok": False, "error": "stack not found"})
            continue
        if await db.publish_queue.find_one({"item_id": it.item_id, "state": {"$in": list(ACTIVE)}}, {"_id": 1}):
            results.append({"item_id": it.item_id, "ok": False, "error": "already in the queue"})
            continue
        n_photos = await db.photos.count_documents({"stack_id": it.item_id})
        if n_photos == 0:
            results.append({"item_id": it.item_id, "ok": False, "error": "no photos: add at least one"})
            continue
        link = vinted_link(stack)
        doc = {"item_id": it.item_id, "card_id": stack["card_id"], "state": "confirmed", "mode": "update" if link else "create",
               "url": link, "payload": {**it.model_dump(), "category": "Single trading cards", "brand": "Pokémon"},
               "photos": min(n_photos, VINTED_MAX_PHOTOS), "error": None,
               "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}
        r = await db.publish_queue.insert_one(doc)
        results.append({"item_id": it.item_id, "ok": True, "id": str(r.inserted_id), "mode": doc["mode"]})
    return {"queued": sum(r["ok"] for r in results), "failed": sum(not r["ok"] for r in results), "results": results}


async def list_queue(db, states: list[str] | None = None, limit: int = 200, item_id: str | None = None) -> list[dict]:
    q: dict = {"state": {"$in": states}} if states else {}
    if item_id:
        q["item_id"] = item_id
    return [_view(d) async for d in db.publish_queue.find(q).sort("created_at", 1).limit(limit)]


async def _write_photos(db, qid: str, stack_id: str, limit: int) -> list[str]:
    """Photos of the stack, cover first, as 01.jpg ... in the temp folder; returns paths relative to the repo root."""
    ps = await photos_svc.list_for_stack(db, stack_id)
    ps.sort(key=lambda p: (not p["cover"], p["order"]))
    folder = _dir(qid)
    await asyncio.to_thread(shutil.rmtree, folder, True)
    await asyncio.to_thread(folder.mkdir, 0o755, True, True)
    names = []
    for n, p in enumerate(ps[:limit], 1):
        data = await photos_svc.image(db, p["id"])
        name = f"{n:02d}.jpg"
        await asyncio.to_thread((folder / name).write_bytes, data)
        names.append(f"publish_tmp/{qid}/{name}")
    return names


async def claim_next(db) -> dict | None:
    """Oldest confirmed item -> publishing (atomic), photos written to the temp folder. None when the queue is empty.
    Refuses to hand out a second item while one is still publishing: the session works one at a time."""
    if await db.publish_queue.find_one({"state": "publishing"}, {"_id": 1}):
        raise QueueError(409, "an item is still publishing: report it (or release it) first")
    d = await db.publish_queue.find_one_and_update(
        {"state": "confirmed"}, {"$set": {"state": "publishing", "updated_at": datetime.now(timezone.utc)}},
        sort=[("created_at", 1)], return_document=True)
    if not d:
        return None
    qid = str(d["_id"])
    try:
        files = await _write_photos(db, qid, d["item_id"], VINTED_MAX_PHOTOS)
        if not files:
            raise QueueError(409, "stack has no photos any more")
    except Exception:
        await db.publish_queue.update_one({"_id": d["_id"]}, {"$set": {"state": "confirmed"}})
        raise
    # the stored link may have been added after confirming: use the current one
    stack = await db.collection_items.find_one({"_id": ObjectId(d["item_id"])}, {"sale": 1})
    link = vinted_link(stack or {}) or d.get("url")
    out = _view(d)
    out.update(files=files, url=link, mode="update" if link else "create",
               open_url=_edit_url(link) if link else f"{VINTED_BASE}/items/new")
    return out


async def release(db, qid: str) -> dict:
    """Give a claimed item back (publishing -> confirmed), e.g. the session stopped on a CAPTCHA."""
    r = await db.publish_queue.find_one_and_update(
        {"_id": _oid(qid), "state": "publishing"}, {"$set": {"state": "confirmed", "updated_at": datetime.now(timezone.utc)}},
        return_document=True)
    if not r:
        raise QueueError(409, "item is not publishing")
    _clean(qid)
    return _view(r)


async def cancel(db, qid: str) -> dict:
    r = await db.publish_queue.find_one_and_update(
        {"_id": _oid(qid), "state": {"$in": list(ACTIVE)}}, {"$set": {"state": "cancelled", "updated_at": datetime.now(timezone.utc)}},
        return_document=True)
    if not r:
        raise QueueError(409, "only confirmed or publishing items can be cancelled")
    _clean(qid)
    return _view(r)


async def report(db, qid: str, body: PublishResultIn) -> dict:
    """The session's result. Published + url saves the stack's Vinted listing (Listed) and keeps its other listings."""
    d = await db.publish_queue.find_one({"_id": _oid(qid)})
    if not d:
        raise QueueError(404, "queue item not found")
    if d["state"] != "publishing":
        raise QueueError(409, f"item is {d['state']}, not publishing")
    if body.state == "published":
        url = body.url or d.get("url")
        if not url:
            raise QueueError(422, "published needs the item url")
        stack = await db.collection_items.find_one({"_id": ObjectId(d["item_id"])})
        if stack:
            p = d["payload"]
            existing = (stack.get("sale") or {}).get("listings") or []
            old = next((l for l in existing if l.get("platform") == "vinted"), {})
            keep = [l for l in existing if l.get("platform") != "vinted"]
            keep = [{k: v for k, v in l.items() if k != "asking_base"} for l in keep]
            mine = {"platform": "vinted", "asking_price": p["price"], "currency": p["currency"], "url": url,
                    "listed_at": old.get("listed_at") or datetime.now(timezone.utc).date().isoformat(),
                    "notes": old.get("notes"), "shipping": old.get("shipping")}
            await sale.set_sale(db, d["item_id"], StackSaleIn(status="listed", listings=[*keep, mine]))
            valuation_cache.bump()
        upd = {"state": "published", "url": url, "error": None}
    else:
        upd = {"state": "failed", "error": body.error or "failed"}
    upd["updated_at"] = datetime.now(timezone.utc)
    r = await db.publish_queue.find_one_and_update({"_id": d["_id"]}, {"$set": upd}, return_document=True)
    _clean(qid)
    return _view(r)


async def retry(db, qid: str) -> dict:
    r = await db.publish_queue.find_one_and_update(
        {"_id": _oid(qid), "state": "failed"}, {"$set": {"state": "confirmed", "error": None, "updated_at": datetime.now(timezone.utc)}},
        return_document=True)
    if not r:
        raise QueueError(409, "only failed items can be retried")
    return _view(r)
