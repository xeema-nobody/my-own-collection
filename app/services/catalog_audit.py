"""Catalog coverage audit: what the provider lists right now vs what the database holds, per set."""
from app.db.mongo import get_db
from app.services.catalog_provider import get_catalog

PROMO_WORDS = ("promo", "black star", "mcdonald", "trainer kit", "futsal", "rumble", "best of game", "southern islands")


def is_promo(s: dict) -> bool:
    name = (s.get("name") or "").lower()
    return (s.get("series") or "") == "Other" or any(w in name for w in PROMO_WORDS)


def classify(provider: dict | None, stored: dict | None, have: int) -> list[str]:
    """Issue tags for one set: `new_at_provider` (provider lists it, we never stored it), `empty` (set doc but no
    cards), `short` (fewer cards than the provider total), `total_changed` (provider total moved since our last
    list), `over_total` (more cards than the provider total: secret rares, harmless), `code_missing` (printed set code known upstream, absent here: typed number + set lookups fail), `gone_upstream`."""
    if provider is None:
        return ["gone_upstream"]
    if stored is None:
        return ["new_at_provider"]
    tags = []
    expected = provider.get("total") or provider.get("printed_total")
    if not have:
        tags.append("empty")
    elif expected and have < expected:
        tags.append("short")
    elif expected and have > expected:
        tags.append("over_total")
    if stored.get("total") != provider.get("total"):
        tags.append("total_changed")
    if provider.get("ptcgo_code") and not stored.get("ptcgo_code"):
        tags.append("code_missing")
    return tags


async def audit(db=None, provider=None) -> dict:
    """One provider `list_sets` call, no card downloads. Rows hold every set with at least one issue plus totals."""
    db = get_db() if db is None else db
    provider = provider or await get_catalog()
    theirs = {s["external_id"]: s for s in await provider.list_sets()}
    ours = {s["external_id"]: s async for s in db.sets.find({"tcg": "pokemon", "language": {"$ne": "ja"}})}
    have = {r["_id"]: r["n"] async for r in db.cards.aggregate(
        [{"$match": {"tcg": "pokemon", "language": {"$ne": "ja"}}}, {"$group": {"_id": "$set.id", "n": {"$sum": 1}}}])}
    rows = []
    for sid in sorted(set(theirs) | set(ours)):
        p, o = theirs.get(sid), ours.get(sid)
        n = have.get(sid, 0)
        tags = classify(p, o, n)
        base = p or o
        rows.append({"id": sid, "name": base.get("name"), "series": base.get("series"), "promo": is_promo(base),
                     "release_date": base.get("release_date"), "provider_total": (p or {}).get("total"),
                     "provider_printed": (p or {}).get("printed_total"), "stored_total": (o or {}).get("total"),
                     "imported": n, "over_printed": max(n - (base.get("printed_total") or n), 0),
                     "missing": max((p or {}).get("total", 0) - n, 0) if p and n else 0, "issues": tags})
    issues = [r for r in rows if set(r["issues"]) - {"over_total"}]
    return {
        "sets": len(rows), "cards": sum(have.values()),
        "provider_only": [r["id"] for r in rows if "new_at_provider" in r["issues"]],
        "short": [r["id"] for r in rows if "short" in r["issues"]],
        "empty": [r["id"] for r in rows if "empty" in r["issues"]],
        "total_changed": [r["id"] for r in rows if "total_changed" in r["issues"]],
        "code_missing": [r["id"] for r in rows if "code_missing" in r["issues"]],
        "promo_sets": sum(1 for r in rows if r["promo"]),
        "secret_over_printed": sum(1 for r in rows if r["over_printed"]),
        "rows": issues,
        "to_import": [r["id"] for r in rows if set(r["issues"]) & {"new_at_provider", "empty", "short", "total_changed", "code_missing"}],
    }
