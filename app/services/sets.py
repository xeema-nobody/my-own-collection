async def sets_with_stats(db, tcg: str | None = None) -> list[dict]:
    """Sets (newest first) with imported card count and how many of those have a price."""
    counts = {r["_id"]: r async for r in db.cards.aggregate([
        {"$group": {"_id": "$set.id", "total": {"$sum": 1},
                    "priced": {"$sum": {"$cond": [{"$ne": ["$price_base", None]}, 1, 0]}}}}])}
    flt = {"tcg": tcg} if tcg else {}
    out = []
    async for s in db.sets.find(flt).sort("release_date", -1):
        c = counts.get(s["external_id"], {})
        out.append({**s, "cards_total": c.get("total", 0), "cards_priced": c.get("priced", 0)})
    return out
