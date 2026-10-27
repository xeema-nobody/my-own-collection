"""Price matrix: newest observation for every (grade, source) of one card."""
from app.providers.price import registry
from app.services.fx import convert

GRADERS = ("PSA", "BGS", "CGC")
KIND_ORDER = {"sold": 0, "market": 1, "ask": 2}  # D-A: sold beats aggregate; never mixed silently


def grade_keys() -> list[str]:
    return ["raw"] + [f"{g}{n}" for g in GRADERS for n in range(10, 0, -1)]


def value_of(p: dict) -> int | None:
    for k in ("market", "median", "avg"):
        if p.get(k) is not None:
            return p[k]
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
    cells = {g: {s: _cell(best.get((g, s)), rates) for s in sources} for g in grade_keys()}
    return {"card_id": card["_id"], "grades": grade_keys(), "sources": sources, "cells": cells}


def _day(p: dict) -> int:
    return int(p["observed_on"].replace("-", ""))


def _cell(p: dict | None, rates: dict) -> dict | None:
    if p is None:
        return None
    price = value_of(p)
    return {"kind": p["kind"], "variant": p.get("variant"), "price": price, "currency": p["currency"],
            "price_base": convert(price, p["currency"], rates), "observed_on": p["observed_on"],
            "as_of": p.get("as_of"), "sample_size": p.get("sample_size"), "url": p.get("url")}
