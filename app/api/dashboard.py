from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query

from app.api.deps import get_db
from app.services import collection as svc
from app.services.movers import movers

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/history")
async def history(days: int = Query(90, ge=1, le=3650)):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    return [{k: v for k, v in s.items() if k != "_id"}
            async for s in get_db().collection_snapshots.find({"date": {"$gte": since}}).sort("date", 1)]


@router.get("/breakdown")
async def breakdown(by: str = "set"):
    rows = await svc.valuate(get_db())
    out: dict[str, int] = {}
    for r in rows:
        if r["value"] is None or not r["card"]:
            continue
        c, it = r["card"], r["item"]
        key = {"set": c["set"]["name"], "rarity": c.get("rarity") or "Unknown", "tcg": c["tcg"],
               "condition": it.get("condition") or "Graded", "language": it["language"]}.get(by, "?")
        out[key] = out.get(key, 0) + r["value"]
    return [{"name": k, "value": v} for k, v in sorted(out.items(), key=lambda x: -x[1])]


@router.get("/movers")
async def top_movers(days: int = Query(7, ge=1, le=365)):
    return await movers(get_db(), days)
