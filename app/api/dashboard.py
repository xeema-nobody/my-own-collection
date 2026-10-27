from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query

from app.api.deps import get_db
from app.services import collection as svc

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
async def movers(days: int = 7):
    db = get_db()
    since = datetime.now(timezone.utc) - timedelta(days=days)
    res = []
    for cid in await db.collection_items.distinct("card_id"):
        pts = [p async for p in db.prices.find(
            {"card_id": cid, "source": "cardmarket", "grade_key": "raw", "as_of": {"$gte": since}}
        ).sort("as_of", 1)]
        if len(pts) < 2 or not pts[0].get("market") or not pts[-1].get("market"):
            continue
        a, b = pts[0]["market"], pts[-1]["market"]
        card = await db.cards.find_one({"_id": cid}, {"name": 1, "images": 1, "set.name": 1})
        res.append({"card_id": cid, "name": card["name"], "set": card["set"]["name"],
                    "images": card.get("images"), "from": a, "to": b, "pct": round((b - a) / a * 100, 2)})
    res.sort(key=lambda r: r["pct"])
    return {"down": res[:5], "up": list(reversed(res[-5:]))}
