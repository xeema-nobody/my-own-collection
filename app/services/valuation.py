"""Per-item valuation: pick the best price for one collection item.

Pure functions (no DB): `collection.valuate` loads cards + recent sales and calls `resolve_item`.

Grade chain, first hit wins (raw items use only step 1):
  exact (PSA9) -> bucket (G9, company-agnostic) -> lower (nearest lower grade, same company)
  -> raw_fallback (raw price) -> none.
Only `exact` is presented as exact; every other match is `estimated`.
Within one grade (D-A): sold if >= `sold_min_sales` sales in the window (median of the last
`sold_sample`), else aggregate market by `preferred_sources`, else thin sold (fewer sales, flagged).
Ask prices are never used. Missing price = None, never 0.
"""
from datetime import datetime, timedelta, timezone
from statistics import median

from app.config import settings
from app.services.fx import convert
from app.services.price_matrix import _BUCKET, _COMPANY
from app.services.pricing import grade_slot, price_entry, price_for

NO_SALES_SOURCES = ("manual",)  # raw sales from scrapers have unknown condition -> only manual counts


def grade_key(item: dict) -> str:
    g = item.get("grading")
    return "raw" if not g else f"{g['company']}{g['grade']:g}"


def preferred(cfg=settings) -> list[str]:
    return [s.strip() for s in cfg.preferred_sources.split(",") if s.strip()]


def _sources(card: dict, cfg) -> list[str]:
    """Market sources in preference order, then any other source that has data."""
    have = {s for s in (card.get("latest_price") or {}) if s != "manual"}
    pref = [s for s in preferred(cfg) if s in have]
    return pref + sorted(have - set(pref))


def _present_grades(card: dict, sales: list[dict]) -> set[str]:
    out = {s["grade_key"] for s in sales}
    for kinds in (card.get("latest_price") or {}).values():
        for kind in ("market", "sold"):
            out |= {g.replace("_", ".") for g in (kinds.get(kind) or {})}
    return out


def _lower_grades(card: dict, sales: list[dict], company: str, grade: float) -> list[str]:
    found = []
    for g in _present_grades(card, sales):
        m = _COMPANY.match(g)
        if m and not _BUCKET.match(g) and m[1].upper() == company.upper() and not m[3] and float(m[2]) < grade:
            found.append((float(m[2]), g))
    return [g for _, g in sorted(found, reverse=True)]


def _sold_pool(sales: list[dict], grade: str, rates: dict, only: str | None) -> list[tuple]:
    """(sold_at, base cents, source) newest first, for one grade, converted to base currency."""
    out = []
    for s in sales:
        if s["grade_key"] != grade or (only and s["source"] != only):
            continue
        if grade == "raw" and s["source"] not in NO_SALES_SOURCES:
            continue
        cents = convert(s["price"], s["currency"], rates)
        if cents is not None:
            out.append((s["sold_at"], cents, s["source"]))
    return sorted(out, reverse=True)


def _stale(entry: dict, cfg, now: datetime) -> bool:
    """Upstream `as_of` older than the cut-off. Scraped points have no `as_of` (dated by our fetch): fresh."""
    as_of = entry.get("as_of")
    if not as_of:
        return False
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    return as_of < now - timedelta(days=cfg.market_max_age_days)


def _market_hit(card, item, grade, rates, cfg, only, now):
    """First fresh market price in source preference order, else the first stale one."""
    stale = None
    for src in ([only] if only else _sources(card, cfg)):
        entry, est = price_entry(card, src, item.get("variant"), grade, "market")
        v, _ = price_for(card, src, item.get("variant"), rates, grade, "market")
        if v is None:
            continue
        hit = {"value": v, "kind": "market", "thin": False, "source": src, "sample_size": None,
               "variant_est": est, "as_of": entry.get("as_of"), "observed_on": entry.get("observed_on"),
               "stale": _stale(entry, cfg, now)}
        if not hit["stale"]:
            return hit
        stale = stale or hit
    return stale


def _price_at(card, item, grade, rates, sales, cfg, only, now=None):
    """Best price for exactly one grade key, or None. Dict: value (per copy), kind, source, thin,
    sample_size, variant_est."""
    pool = _sold_pool(sales, grade, rates, only)
    if len(pool) >= cfg.sold_min_sales:
        last = pool[: cfg.sold_sample]
        return {"value": round(median(c for _, c, _ in last)), "kind": "sold", "thin": False,
                "source": "+".join(sorted({s for *_, s in last})), "sample_size": len(last),
                "variant_est": False, "as_of": last[0][0], "observed_on": None, "stale": False}
    variant = item.get("variant")
    hit = _market_hit(card, item, grade, rates, cfg, only, now or datetime.now(timezone.utc))
    if hit:
        return hit
    if pool:
        last = pool[: cfg.sold_sample]
        return {"value": round(median(c for _, c, _ in last)), "kind": "sold", "thin": True,
                "source": "+".join(sorted({s for *_, s in last})), "sample_size": len(last),
                "variant_est": False, "as_of": last[0][0], "observed_on": None, "stale": False}
    for src in ([only] if only else _sources(card, cfg)):
        v, est = price_for(card, src, variant, rates, grade, "sold")
        if v is not None:
            entry, _ = price_entry(card, src, variant, grade, "sold")
            return {"value": v, "kind": "sold", "thin": True, "source": src, "sample_size": None,
                    "variant_est": est, "as_of": entry.get("as_of"), "observed_on": entry.get("observed_on"),
                    "stale": False}
    return None


def _chain(card, item, sales, gk) -> list[tuple[str, str]]:
    if gk == "raw":
        return [("exact", "raw")]
    g = item["grading"]
    steps = [("exact", gk)]
    if g["grade"] < 10:
        steps.append(("bucket", f"G{g['grade']:g}"))
    steps += [("lower", k) for k in _lower_grades(card, sales, g["company"], g["grade"])]
    steps.append(("raw_fallback", "raw"))
    return steps


def resolve_item(card: dict | None, item: dict, rates: dict, sales: list[dict], cfg=settings,
                 only: str | None = None, now: datetime | None = None) -> dict:
    """Value of the whole stack (quantity applied, base-currency cents). `only` restricts to one source;
    `now` is the valuation date (staleness cut-off), default today."""
    gk = grade_key(item)
    none = {"value": None, "price_kind": None, "source": None, "match": "none", "grade_key_used": None,
            "estimated": False, "thin": False, "sample_size": None, "as_of": None, "observed_on": None,
            "stale": False, "headline_rule": None}
    if not card:
        return none
    # raw_fallback passes no sales: scraped raw sales have unknown condition
    for match, g in _chain(card, item, sales, gk):
        hit = _price_at(card, item, g, rates, sales if match != "raw_fallback" else [], cfg, only, now)
        if hit:
            return {"value": hit["value"] * item["quantity"], "price_kind": hit["kind"],
                    "source": hit["source"], "match": match, "grade_key_used": g,
                    "estimated": match != "exact" or hit["variant_est"],
                    "thin": hit["thin"], "sample_size": hit["sample_size"], "as_of": hit["as_of"],
                    "observed_on": hit["observed_on"], "stale": hit["stale"],
                    "headline_rule": headline_rule(hit, only, cfg)}
    return none


def headline_rule(hit: dict, only: str | None, cfg=settings) -> str:
    """Why this price won (shown next to the headline value)."""
    if only:
        return f"only {only}"
    n = hit["sample_size"]
    if hit["kind"] == "sold":
        if hit["thin"]:
            return f"thin sold: {n} sale{'s' if n != 1 else ''}, no market price" if n else "thin sold point, no market price"
        return f"sold median of last {n} (>= {cfg.sold_min_sales} sales in {cfg.sold_window_days} d)"
    pref = preferred(cfg)
    rank = f"#{pref.index(hit['source']) + 1} in preference order" if hit["source"] in pref else "not in preference order"
    stale = "; fresher sources lacked this grade" if hit.get("stale") else ""
    return f"market price: {hit['source']} ({rank}){stale}"


def spread(values: dict[str, int | None], cfg=settings) -> dict:
    """Median/min/max over sources with a value; a source is an outlier when it is more than
    `outlier_pct` % from the median and at least 3 sources have a value."""
    have = {s: v for s, v in values.items() if v is not None}
    if not have:
        return {"median": None, "min": None, "max": None, "outliers": [], "pct": {}}
    med = median(have.values())
    pct = {s: round((v - med) / med * 100) for s, v in have.items()} if med else {}
    out = [s for s, p in pct.items() if len(have) >= 3 and abs(p) > cfg.outlier_pct]
    return {"median": round(med), "min": min(have.values()), "max": max(have.values()),
            "outliers": sorted(out), "pct": pct}
