"""Slab identity from the cert: look the cert up at the grader (cached in Mongo), then match the catalog by
name + number + printed total (+ set / year bonus). Never auto-adds; PSA / BGS pages lack a number or a total, so
their best match is "likely" and always needs the user's confirm."""
import logging
import re
from datetime import datetime, timedelta, timezone

from app.providers.catalog.common import norm
from app.providers.fetcher import FetcherClient
from app.providers.grading import registry
from app.providers.grading.base import (BLOCKED, FOUND, INVALID, LINK_ONLY, NOT_FOUND, UNAVAILABLE, CertInfo,
                                        clean_cert, now)

log = logging.getLogger(__name__)
# How long a cert answer is trusted. Blocked / unavailable / invalid are never stored (retry on the next scan).
TTL = {FOUND: timedelta(days=30), NOT_FOUND: timedelta(hours=1), LINK_ONLY: timedelta(days=7)}
POOL = 200
MAX_CARDS = 12
WEIGHT = {"name": 1.0, "number": 4.0, "total": 3.0, "set": 2.0, "year": 1.0}
CONFIRM_ALWAYS = {"PSA", "BGS"}  # the page lacks the printed total (PSA) or the number (BGS): never "exact"
# words a grader prints after the name that are not part of it
TRAIL = re.compile(r"\b(?:reverse holo|holo(?:foil)?|1st edition|first edition|shadowless|unlimited"
                   r"|sir|sar|ar|ur|hr|sr|rr|full art|alt(?:ernate)? art|special illustration rare|secret rare)\b")


def _key(grader: str, cert: str) -> str:
    return f"{grader}:{cert}"


def _expiry(status: str) -> datetime | None:
    ttl = TTL.get(status)
    return now() + ttl if ttl else None


def _aware(d: datetime | None) -> datetime | None:
    return d if d is None or d.tzinfo else d.replace(tzinfo=timezone.utc)


async def cached_info(db, grader: str, cert: str) -> CertInfo | None:
    d = await db.cert_cache.find_one({"_id": _key(grader, cert)})
    exp = _aware(d.get("expires_at")) if d else None
    if not d or exp is None or exp <= now():
        return None
    return CertInfo.from_doc(d["info"])


async def fetch_info(db, grader: str, cert: str, client: FetcherClient | None = None, transport=None,
                     refresh: bool = False) -> tuple[CertInfo, bool]:
    """(info, from_cache). Bad grader / cert -> invalid without a request. Counts every lookup per grader so
    link-only graders (no reader yet) show up in `cert_cache`."""
    g, c = registry.canon_grader(grader), clean_cert(cert)
    if c is None or not g:
        return CertInfo(g, (cert or "").strip(), INVALID, None, detail="grader and a digits-only cert are needed",
                        fetched_at=now()), False
    if not refresh and (hit := await cached_info(db, g, c)):
        await db.cert_cache.update_one({"_id": _key(g, c)}, {"$inc": {"lookups": 1}})
        return hit, True
    info = await registry.lookup(g, c, client, transport)
    exp = _expiry(info.status)
    if exp is not None:
        await db.cert_cache.update_one(
            {"_id": _key(g, c)},
            {"$set": {"grader": info.grader, "cert": c, "status": info.status, "info": info.to_doc(),
                      "fetched_at": info.fetched_at or now(), "expires_at": exp}, "$inc": {"lookups": 1}},
            upsert=True)
    return info, False


def name_forms(name: str | None) -> list[str]:
    """Normalised spellings of a printed name that the catalog might hold: 'BLASTOISE-EX' -> 'blastoise ex'."""
    n = norm(name or "")
    n = TRAIL.sub(" ", n)
    forms: list[str] = []
    for f in (n, re.sub(r"-(ex|gx|v|vmax|vstar|break)\b", r" \1", n), re.sub(r"[^a-z0-9' ]", " ", n)):
        f = re.sub(r"\s+", " ", f).strip()
        if f and f not in forms:
            forms.append(f)
    return forms


def _toks(s: str | None) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", norm(s or ""))) - {"the", "and", "tcg", "pokemon"}


def signals(info: CertInfo, card: dict, name_hit: bool) -> list[str]:
    from app.services import scan
    s = card.get("set") or {}
    sig = ["name"] if name_hit else []
    left = (info.number or "").split("/")[0].strip()
    have_no = card.get("number")
    if left and (scan._num(have_no) == scan._num(left)
                 or (not re.search(r"[a-z]", f"{left}{have_no}", re.I) and scan._digits(have_no) == scan._digits(left))):
        sig.append("number")
    if info.printed_total and s.get("printed_total") == info.printed_total:
        sig.append("total")
    want, have = _toks(info.set_name), _toks(s.get("name"))
    if want and have and (want <= have or have <= want or len(want & have) >= max(2, len(want) - 1)):
        sig.append("set")
    rd = s.get("release_date")
    year = rd.year if hasattr(rd, "year") else (int(str(rd)[:4]) if rd else None)
    if info.year and year == info.year:
        sig.append("year")
    return sig


def score(sig: list[str]) -> float:
    return sum(WEIGHT[x] for x in sig)


def how_exact(grader: str, cards: list[dict]) -> str:
    """exact | likely | possible | none. Exact: name + number + total agree on exactly one print (ACE only)."""
    if not cards:
        return "none"
    top = cards[0]["signals"]
    unique = len(cards) == 1 or score(cards[1]["signals"]) < score(top)
    if {"name", "number", "total"} <= set(top) and unique:
        return "likely" if grader in CONFIRM_ALWAYS else "exact"
    if "name" in top and ("number" in top or "total" in top or "set" in top) and unique:
        return "likely"
    return "possible"


async def match_catalog(db, info: CertInfo) -> list[dict]:
    """Catalog prints for a found cert, best first, each with `signals` and `match_label`."""
    from app.services import scan
    forms = name_forms(info.name)
    found: list[dict] = []
    name_hit = False
    if forms:
        found = [c async for c in db.cards.find({"tcg": "pokemon", "name_norm": {"$in": forms}}, {"raw": 0}).limit(POOL)]
        name_hit = bool(found)
    if not found and info.number and info.printed_total:
        found = [c async for c in db.cards.find(
            {"tcg": "pokemon", "set.printed_total": info.printed_total,
             "number": {"$in": scan._number_forms(info.number.split("/")[0])}}, {"raw": 0}).limit(MAX_CARDS)]
    sigs = {c["_id"]: signals(info, c, name_hit) for c in found}
    stamp = lambda c: str((c.get("set") or {}).get("release_date") or "")  # noqa: E731
    found.sort(key=stamp, reverse=True)
    found.sort(key=lambda c: -score(sigs[c["_id"]]))
    top = found[:MAX_CARDS]
    cards = await scan.views(db, top)
    for c, v in zip(top, cards):
        v["signals"] = sigs[c["_id"]]
        v["match_label"] = scan.label_for(v["signals"])
    cards.sort(key=lambda v: (-score(v["signals"]), -v["owned_qty"]))
    for v in cards:  # the grader's variant ('Holo') picks the matching variant of the print, never invents one
        want = norm(info.variant or "")
        v["variant_hint"] = next((x for x in v["variants"] if want and (want in norm(x) or norm(x) in want)), None)
    return cards


async def lookup(db, grader: str, cert: str, client: FetcherClient | None = None, transport=None,
                 refresh: bool = False) -> dict:
    """`{cert: CertInfo doc, cards, how_exact, needs_confirm, cached}`; the cards are only listed for a found cert."""
    info, cached = await fetch_info(db, grader, cert, client, transport, refresh)
    cards = await match_catalog(db, info) if info.status == FOUND else []
    level = how_exact(info.grader, cards)
    return {"cert": info.to_doc(), "cards": cards, "how_exact": level, "cached": cached,
            "needs_confirm": level != "none" and (level != "exact" or info.grader in CONFIRM_ALWAYS),
            "report_url": info.url}


async def enrich_grading(db, grading: dict | None) -> dict | None:
    """Stored grading sub-document: the report link (fixed template) and the cached cert page, if any. Both are
    derived on the server, never taken from the request."""
    if not grading or not grading.get("cert_number"):
        return grading
    g = registry.canon_grader(grading.get("company"))
    c = clean_cert(grading["cert_number"])
    url = registry.report_url(g, c) if c else None
    info = await cached_info(db, g, c) if c and url else None
    out = {k: v for k, v in grading.items() if k not in ("report_url", "cert_info")}
    out["report_url"] = url
    out["cert_info"] = info.to_doc() if info and info.status == FOUND else None
    return out
