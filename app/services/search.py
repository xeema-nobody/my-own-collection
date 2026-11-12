import re

from app.providers.catalog.common import norm

NUM_RE = re.compile(r"^#?(\d+[a-z]*)(?:/(\d+))?$")
ID_RE = re.compile(r"^[a-z0-9]+-[a-z0-9]+$")


def build_query(q: str | None, tcg=None, set_id=None, type_=None, rarity=None, supertype=None,
                price_min: int | None = None, price_max: int | None = None,
                has_price: bool | None = None, owned_ids: list[str] | None = None,
                language: str | None = None) -> dict:
    conds: list[dict] = []
    for raw in (q or "").lower().split():
        tok = norm(raw)
        if not tok:  # kana / kanji: norm() drops them, search the native text as typed
            conds.append({"search_text": {"$regex": re.escape(raw)}})
            continue
        if ID_RE.match(tok) and any(ch.isdigit() for ch in tok):
            conds.append({"external_id": {"$regex": f"^{re.escape(tok)}$", "$options": "i"}})  # ja codes: 'SV2a-151'
            continue
        m = NUM_RE.match(tok)
        if m and (m.group(2) or tok.startswith("#")):
            conds.append({"number": {"$regex": f"^0*{re.escape(m.group(1))}$", "$options": "i"}})
            if m.group(2):
                conds.append({"set.printed_total": int(m.group(2))})
            continue
        conds.append({"search_text": {"$regex": re.escape(tok)}})
    if tcg:
        conds.append({"tcg": tcg})
    if language:
        conds.append({"language": language})
    if set_id:
        ids = [x for x in set_id.split(",") if x]   # several sets: 'sv1,svp' (pull search in a multi-set product)
        conds.append({"set.id": ids[0] if len(ids) == 1 else {"$in": ids}} if ids else {"set.id": set_id})
    if type_:
        conds.append({"types": type_})
    if rarity:
        conds.append({"rarity": rarity})
    if supertype:
        conds.append({"supertype": supertype})
    if price_min is not None or price_max is not None:
        r = {}
        if price_min is not None:
            r["$gte"] = price_min
        if price_max is not None:
            r["$lte"] = price_max
        conds.append({"price_base": r})
    if has_price is not None:
        conds.append({"price_base": {"$ne": None}} if has_price else {"price_base": None})
    if owned_ids is not None:
        conds.append({"_id": {"$in": owned_ids}})
    return {"$and": conds} if conds else {}


def exclude_sealed(flt: dict) -> dict:
    """Card search never lists sealed products (they have their own catalog, services/sealed.py)."""
    return {"$and": [{"kind": {"$ne": "sealed"}}, *flt.get("$and", [])]}


SORTS = {
    "name": [("name_norm", 1)], "number": [("set.release_date", -1), ("set.id", 1), ("number_sort", 1)],
    "release": [("set.release_date", -1), ("set.id", 1), ("number_sort", 1)],
    "price_desc": [("price_base", -1), ("_id", 1)], "price_asc": [("price_base", 1), ("_id", 1)],
}
NULL_LAST = 1 << 62  # sentinel so unpriced cards sort after priced ones in ascending order


async def find_page(db, flt: dict, sort: str, skip: int, limit: int) -> list[dict]:
    """One page of cards. Mongo sorts null first ascending, so price_asc sorts on a null-last key."""
    if sort == "price_asc":
        pipe = [{"$match": flt}, {"$project": {"raw": 0}},
                {"$addFields": {"_s": {"$ifNull": ["$price_base", NULL_LAST]}}},
                {"$sort": {"_s": 1, "_id": 1}}, {"$skip": skip}, {"$limit": limit},
                {"$project": {"_s": 0}}]
        return [c async for c in db.cards.aggregate(pipe)]
    cur = db.cards.find(flt, {"raw": 0}).sort(SORTS.get(sort, SORTS["release"])).skip(skip).limit(limit)
    return [c async for c in cur]
