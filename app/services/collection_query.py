"""Filter / sort / page / total / facets over valuated collection rows (`collection.valuate` output).

Pure functions over the cached rows (services/valuation_cache.py), so a warm request costs a few ms
even at 10k stacks. Money = integer cents. Rows are read-only."""
from dataclasses import dataclass, field

from app.providers.catalog.common import norm
from app.services import acquisition
from app.services.collection import present

SORTS = ("added", "value", "cost", "pl", "qty", "name", "set", "updated")
DEFAULT_DESC = {"added", "value", "cost", "pl", "qty", "updated"}


@dataclass
class Query:
    q: str | None = None
    tcg: str | None = None
    set: str | None = None
    rarity: str | None = None
    type: str | None = None
    language: str | None = None
    condition: str | None = None
    graded: bool | None = None
    grader: str | None = None
    grade: str | None = None
    acquisition: str | None = None          # purchased|pulled|traded|gift|other|unset
    cost_missing: bool | None = None
    needs_price: bool | None = None
    stale: bool | None = None
    price_min: int | None = None            # cents per copy
    price_max: int | None = None
    pl: str | None = None                   # positive | negative
    card_id: str | None = None
    sort: str = "added"
    order: str | None = None
    page: int = 1
    page_size: int = 50
    extra: dict = field(default_factory=dict)


def grade_str(g) -> str:
    """9.0 -> "9", 9.5 -> "9.5" (grades are stored as numbers, filtered as text)."""
    return f"{g:g}" if isinstance(g, (int, float)) else str(g)


def _pl(r: dict) -> int | None:
    return None if r["value"] is None or r["cost"] is None else r["value"] - r["cost"]


def _unit(r: dict) -> float | None:
    return None if r["value"] is None else r["value"] / r["item"]["quantity"]


def _updated(r: dict) -> str | None:
    """Date of the price behind the value (observed_on, else upstream as_of)."""
    if r.get("observed_on"):
        return str(r["observed_on"])[:10]
    a = r.get("as_of")
    return a.strftime("%Y-%m-%d") if a is not None and hasattr(a, "strftime") else None


def _card(r: dict) -> dict:
    return r["card"] or {}


def _matches(r: dict, q: Query, text: str) -> bool:
    it, c = r["item"], _card(r)
    g = it.get("grading")
    if q.card_id and it["card_id"] != q.card_id:
        return False
    if q.graded is not None and bool(g) != q.graded:
        return False
    if q.language and it.get("language") != q.language:
        return False
    if q.condition and it.get("condition") != q.condition:
        return False
    if q.grader and (not g or g.get("company") != q.grader):
        return False
    if q.grade and (not g or grade_str(g.get("grade")) != q.grade):
        return False
    if q.acquisition and ((it.get("acquired") or {}).get("type")) != (None if q.acquisition == "unset" else q.acquisition):
        return False
    if q.cost_missing is not None and (r["cost"] is None) != q.cost_missing:
        return False
    if q.needs_price is not None and r["needs_price"] != q.needs_price:
        return False
    if q.stale is not None and bool(r.get("stale")) != q.stale:
        return False
    if q.pl:
        pl = _pl(r)
        if pl is None or (pl <= 0 if q.pl == "positive" else pl >= 0):
            return False
    if q.price_min is not None or q.price_max is not None:
        u = _unit(r)
        if u is None or (q.price_min is not None and u < q.price_min) or (q.price_max is not None and u > q.price_max):
            return False
    if q.tcg and c.get("tcg") != q.tcg:
        return False
    if q.set and (c.get("set") or {}).get("id") != q.set:
        return False
    if q.rarity and c.get("rarity") != q.rarity:
        return False
    if q.type and q.type not in (c.get("types") or []):
        return False
    if text and text not in (c.get("search_text") or ""):
        return False
    return True


SORT_KEYS = {
    "added": lambda r: r["item"]["created_at"],
    "value": lambda r: r["value"],
    "cost": lambda r: r["cost"],
    "pl": _pl,
    "qty": lambda r: r["item"]["quantity"],
    "name": lambda r: _card(r).get("name_norm") if _card(r) else None,
    "set": lambda r: ((_card(r).get("set") or {}).get("name", ""), _card(r).get("number_sort", 0), _card(r).get("number", ""))
        if _card(r) else None,
    "updated": _updated,
}


def sort_rows(rows: list[dict], sort: str, order: str | None) -> list[dict]:
    """Sort by `sort`; stacks with no value for that key (None) always go last. Ties keep the
    newest-first order of the stack id so paging is stable."""
    key = SORT_KEYS.get(sort, SORT_KEYS["added"])
    desc = (order == "desc") if order else sort in DEFAULT_DESC
    ordered = sorted(rows, key=lambda r: str(r["item"]["_id"]))  # stable base order
    have = [r for r in ordered if key(r) is not None]
    rest = [r for r in ordered if key(r) is None]
    return sorted(have, key=key, reverse=desc) + rest


def totals(rows: list[dict]) -> dict:
    cs = acquisition.cost_stats(rows)
    return {"stacks": len(rows), "cards": sum(r["item"]["quantity"] for r in rows),
            "value": sum(r["value"] or 0 for r in rows), "cost": cs["cost"], "pl": cs["pl"],
            "pl_ex_pulled": cs["pl_ex_pulled"], "cost_basis_cost": cs["cost_basis_cost"],
            "cost_basis_cost_ex_pulled": cs["cost_basis_cost_ex_pulled"], "cost_missing": cs["cost_missing"],
            "needs_price": sum(1 for r in rows if r["needs_price"]),
            "unpriced": sum(1 for r in rows if r["value"] is None)}


def query(rows: list[dict], q: Query) -> dict:
    text = norm(q.q) if q.q else ""
    hit = [r for r in rows if _matches(r, q, text)]
    hit = sort_rows(hit, q.sort, q.order)
    page = hit[(q.page - 1) * q.page_size: q.page * q.page_size]
    return {"total": len(hit), "items": [present(r) for r in page], "totals": totals(hit)}


def facets(rows: list[dict]) -> dict:
    """Distinct values with stack counts for the filter dropdowns (whole collection)."""
    def count(values) -> list[dict]:
        out: dict[str, int] = {}
        for v in values:
            if v not in (None, ""):
                out[v] = out.get(v, 0) + 1
        return [{"value": k, "count": n} for k, n in sorted(out.items())]

    sets: dict[str, dict] = {}
    for r in rows:
        s = _card(r).get("set") or {}
        if s.get("id"):
            e = sets.setdefault(s["id"], {"value": s["id"], "label": s.get("name") or s["id"], "count": 0})
            e["count"] += 1
    gr = [r["item"]["grading"] for r in rows if r["item"].get("grading")]
    grades = count(grade_str(g.get("grade")) for g in gr)
    grades.sort(key=lambda e: float(e["value"]) if e["value"].replace(".", "", 1).isdigit() else -1, reverse=True)
    return {"sets": sorted(sets.values(), key=lambda e: e["label"].lower()),
            "rarities": count(_card(r).get("rarity") for r in rows),
            "types": count(t for r in rows for t in (_card(r).get("types") or [])),
            "languages": count(r["item"].get("language") for r in rows),
            "conditions": count(r["item"].get("condition") for r in rows),
            "graders": count(g.get("company") for g in gr), "grades": grades}
