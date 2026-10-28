from collections import defaultdict
from datetime import datetime, timezone

from app.config import settings
from app.services.collection import source_ids, valuate


async def take_snapshot(db) -> dict:
    """Idempotent per UTC date. Same valuation as the collection screens (graded-aware)."""
    vals = await valuate(db)
    srcs = [s for s in source_ids() if any(v["values"][s] is not None for v in vals)]
    totals = {s: 0 for s in srcs}
    unpriced = {s: 0 for s in srcs}
    by_kind: dict[str, int] = defaultdict(int)
    by_set, by_rarity, by_tcg = defaultdict(int), defaultdict(int), defaultdict(int)
    for v in vals:
        for s in srcs:
            if v["values"][s] is None:
                unpriced[s] += 1
            else:
                totals[s] += v["values"][s]
        if v["value"] is not None:
            by_kind[v["price_kind"]] += v["value"]
        if v["value"] is not None and v["card"]:
            by_set[v["card"]["set"]["name"]] += v["value"]
            by_rarity[v["card"].get("rarity") or "Unknown"] += v["value"]
            by_tcg[v["card"]["tcg"]] += v["value"]
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    doc = {"date": date, "base_currency": settings.base_currency, "totals_by_source": totals,
           "total_value": sum(v["value"] or 0 for v in vals), "value_kind_breakdown": dict(by_kind),
           "estimated_count": sum(1 for v in vals if v["estimated"]),
           "total_cost": sum(v["cost"] or 0 for v in vals), "item_count": len(vals),
           "card_count": sum(v["item"]["quantity"] for v in vals), "unpriced_count": unpriced,
           "breakdowns": {"by_set": dict(by_set), "by_rarity": dict(by_rarity), "by_tcg": dict(by_tcg)},
           "taken_at": datetime.now(timezone.utc)}
    await db.collection_snapshots.update_one({"date": date}, {"$set": doc}, upsert=True)
    return doc
