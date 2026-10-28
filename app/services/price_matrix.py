"""Price matrix: newest observation for every (grade, source) of one card."""
import re

from app.providers.price import registry
from app.services.fx import convert

GRADERS = ("PSA", "BGS", "CGC")
KIND_ORDER = {"sold": 0, "market": 1, "ask": 2}  # D-A: sold beats aggregate; never mixed silently


def grade_keys() -> list[str]:
    return ["raw"] + [f"{g}{n}" for g in GRADERS for n in range(10, 0, -1)]


_BUCKET = re.compile(r"^G(\d+(?:\.\d+)?)$")                       # PriceCharting company-agnostic bucket
_COMPANY = re.compile(r"^([A-Za-z]+?)(\d+(?:\.\d+)?)([A-Za-z]*)$")  # PSA10, BGS9.5, BGS10Black


def _grade_sort(g: str) -> tuple:
    if g == "raw":
        return (0,)
    if m := _BUCKET.match(g):
        return (1, -float(m[1]))
    if m := _COMPANY.match(g):
        c = m[1].upper()
        return (2, GRADERS.index(c) if c in GRADERS else len(GRADERS), c, -float(m[2]), m[3])
    return (3, g)


def grades_for(rows: list[dict]) -> tuple[list[str], list[str]]:
    """Matrix row keys (fixed baseline + every grade stored for the card) and the companies present."""
    grades = sorted(set(grade_keys()) | {p["grade_key"] for p in rows}, key=_grade_sort)
    graders: list[str] = []
    for g in grades:
        m = _COMPANY.match(g)
        if m and not _BUCKET.match(g) and m[1].upper() not in graders:
            graders.append(m[1].upper())
    return grades, graders


def value_of(p: dict) -> int | None:
    for k in ("market", "median", "avg"):
        if p.get(k) is not None:
            return p[k]
    if p.get("kind") == "ask":   # Cardmarket "From" is stored as `low` only
        return p.get("low")
    return None


def _rank(p: dict, variants: list[str]) -> tuple:
    v = p.get("variant")
    vi = -1 if v is None else variants.index(v) if v in variants else len(variants)
    return (KIND_ORDER.get(p["kind"], 9), vi)


def build_matrix(card: dict, rows: list[dict], rates: dict) -> dict:
    """`rows` = all prices for the card. One cell per (grade, source): newest day, then sold>market>ask,
    then the card's first variant. Cells without any price are None."""
    variants = card.get("variants") or []
    best: dict[tuple, dict] = {}
    for p in rows:
        if value_of(p) is None:
            continue
        k = (p["grade_key"], p["source"])
        cur = best.get(k)
        if cur is None or (-_day(p), _rank(p, variants)) < (-_day(cur), _rank(cur, variants)):
            best[k] = p
    sources = [s.id for s in registry()]
    sources += sorted({p["source"] for p in rows} - set(sources))
    grades, graders = grades_for(rows)
    cells = {g: {s: _cell(best.get((g, s)), rates) for s in sources} for g in grades}
    return {"card_id": card["_id"], "grades": grades, "graders": graders, "sources": sources, "cells": cells}


def _day(p: dict) -> int:
    return int(p["observed_on"].replace("-", ""))


def _cell(p: dict | None, rates: dict) -> dict | None:
    if p is None:
        return None
    price = value_of(p)
    return {"kind": p["kind"], "variant": p.get("variant"), "price": price, "currency": p["currency"],
            "price_base": convert(price, p["currency"], rates), "observed_on": p["observed_on"],
            "as_of": p.get("as_of"), "sample_size": p.get("sample_size"), "url": p.get("url"),
            "fetched_at": p.get("fetched_at"), "seed": bool(p.get("seed"))}
