import re

from app.providers.catalog.pokemontcg import norm

NUM_RE = re.compile(r"^#?(\d+[a-z]*)(?:/(\d+))?$")
ID_RE = re.compile(r"^[a-z0-9]+-[a-z0-9]+$")


def build_query(q: str | None, tcg=None, set_id=None, type_=None, rarity=None, supertype=None,
                price_min: int | None = None, price_max: int | None = None,
                owned_ids: list[str] | None = None) -> dict:
    conds: list[dict] = []
    for tok in norm(q or "").split():
        if ID_RE.match(tok) and any(ch.isdigit() for ch in tok):
            conds.append({"external_id": tok})
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
    if set_id:
        conds.append({"set.id": set_id})
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
    if owned_ids is not None:
        conds.append({"_id": {"$in": owned_ids}})
    return {"$and": conds} if conds else {}


SORTS = {
    "name": [("name_norm", 1)], "number": [("set.release_date", -1), ("set.id", 1), ("number_sort", 1)],
    "release": [("set.release_date", -1), ("set.id", 1), ("number_sort", 1)],
    "price_desc": [("price_base", -1)], "price_asc": [("price_base", 1)],
}
