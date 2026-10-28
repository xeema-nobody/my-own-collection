"""Top movers: each owned item valued now vs `days` ago with the same resolver as the collection
screens (graded-aware, sold-based). Past value = observation log + sales as of that date."""
from datetime import datetime, timedelta, timezone

from app.services.collection import valuate


def comparable(old: dict, new: dict) -> bool:
    """Both ends priced the same way: a changed grade match or price kind is a data gap, not a move."""
    return (old["value"] is not None and new["value"] is not None and old["value"] > 0
            and old["match"] == new["match"] and old["grade_key_used"] == new["grade_key_used"]
            and old["price_kind"] == new["price_kind"])


async def movers(db, days: int = 7, limit: int = 5) -> dict:
    past = datetime.now(timezone.utc) - timedelta(days=days)
    old = {v["item"]["_id"]: v for v in await valuate(db, as_of=past)}
    res = []
    for new in await valuate(db):
        o = old.get(new["item"]["_id"])
        if not o or not new["card"] or not comparable(o, new):
            continue
        a, b = o["value"], new["value"]
        if a == b:
            continue
        c = new["card"]
        res.append({"card_id": c["_id"], "name": c["name"], "set": c["set"]["name"], "images": c.get("images"),
                    "grade_key": new["grade_key_used"], "kind": new["price_kind"], "source": new["source"],
                    "match": new["match"], "from": a, "to": b, "pct": round((b - a) / a * 100, 2)})
    res.sort(key=lambda r: r["pct"])
    return {"down": [r for r in res if r["pct"] < 0][:limit],
            "up": [r for r in reversed(res) if r["pct"] > 0][:limit]}
