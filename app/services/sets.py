def language_filter(language: str | None) -> dict:
    """None = the English catalog (Japanese sets are managed on their own: ids can repeat), 'all' = both."""
    return {} if language == "all" else {"language": language} if language and language != "en" else {"language": {"$ne": "ja"}}


async def sets_with_stats(db, tcg: str | None = None, language: str | None = None) -> list[dict]:
    """Sets (newest first) with imported card count and how many of those have a price."""
    lf = language_filter(language)
    counts = {r["_id"]: r async for r in db.cards.aggregate([
        {"$match": lf}, {"$group": {"_id": "$set.id", "total": {"$sum": 1},
                    "priced": {"$sum": {"$cond": [{"$ne": [{"$ifNull": ["$price_base", None]}, None]}, 1, 0]}}}}])}   # absent price_base = unpriced
    flt = {**lf, **({"tcg": tcg} if tcg else {})}
    out = []
    async for s in db.sets.find(flt).sort("release_date", -1):
        c = counts.get(s["external_id"], {})
        have, expected = c.get("total", 0), s.get("total") or s.get("printed_total")
        out.append({**s, "cards_total": have, "cards_priced": c.get("priced", 0), "cards_expected": expected,
                    "cards_missing": max(expected - have, 0) if expected and have else 0,
                    "complete": not (expected and have and have < expected)})
    return out
