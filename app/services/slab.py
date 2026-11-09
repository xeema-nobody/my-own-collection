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
WEIGHT = {"name": 1.0, "number": 4.0, "total": 3.0, "set": 2.0, "year": 1.0, "rarity": 2.0}
CONFIRM_ALWAYS = {"PSA", "BGS"}  # the page lacks the printed total (PSA) or the number (BGS): never "exact"
# Page rarity words / abbreviations -> the token set of the catalog rarity they mean (order of tokens is free:
# the catalog says "Rare Secret", the page "Secret Rare"). Longest phrase first. A bonus signal, never a filter.
_SIR, _IR = frozenset({"special", "illustration", "rare"}), frozenset({"illustration", "rare"})
_HR, _UR = frozenset({"hyper", "rare"}), frozenset({"ultra", "rare"})
_SECRET, _DR = frozenset({"secret", "rare"}), frozenset({"double", "rare"})
RARITY_PHRASES: list[tuple[tuple[str, ...], frozenset]] = [
    (("special", "illustration", "rare"), _SIR), (("special", "art", "rare"), _SIR), (("illustration", "rare"), _IR),
    (("hyper", "rare"), _HR), (("ultra", "rare"), _UR), (("secret", "rare"), _SECRET), (("double", "rare"), _DR),
    (("sir",), _SIR), (("sar",), _SIR), (("ar",), _IR), (("hr",), _HR), (("ur",), _UR), (("sr",), _SECRET),
    (("rr",), _DR)]
# Page words that are not part of a card's name: rarity words, finishes, edition and language marks, brand words.
NOISE = ({w for ph, _ in RARITY_PHRASES for w in ph}
         | {"holo", "holofoil", "reverse", "foil", "1st", "first", "edition", "shadowless", "unlimited", "full",
            "alt", "alternate", "art", "rare", "english", "japanese", "jpn", "jp", "en", "promo", "pokemon", "tcg",
            "game", "card"})
# Set-name words shared by many sets (series names): they count for less when ranking sets.
GENERIC_SET = {"scarlet", "violet", "sword", "shield", "sun", "moon", "xy", "black", "white", "diamond", "pearl",
               "platinum", "base", "set", "ex", "series"}
SET_NOISE = NOISE | {"and", "the", "of", "a"}
SET_CACHE_TTL = timedelta(minutes=10)
_sets_cache: tuple[datetime, list[dict]] | None = None


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


def words(s: str | None) -> list[str]:
    """Lowercase ascii words of a printed text: accents stripped, punctuation splits, apostrophes join ("Mr. Mime" -> mr mime, "Farfetch'd" -> farfetchd)."""
    return re.findall(r"[a-z0-9]+", norm(s or "").replace("'", ""))


def page_rarity(*texts: str | None) -> frozenset | None:
    """The catalog rarity (token set) a page name / variety hints at: 'Gardevoir ex SIR' -> special illustration rare."""
    w = words(" ".join(t for t in texts if t))
    for ph, toks in RARITY_PHRASES:
        n = len(ph)
        if any(tuple(w[i:i + n]) == ph for i in range(len(w) - n + 1)):
            return toks
    return None


def reset_sets_cache() -> None:
    global _sets_cache
    _sets_cache = None


async def _sets(db) -> list[dict]:
    """Every Pokémon set in the catalog (id, name, release year, printed total), refreshed every 10 minutes."""
    global _sets_cache
    if _sets_cache and now() - _sets_cache[0] < SET_CACHE_TTL:
        return _sets_cache[1]
    out = []
    async for d in db.cards.aggregate([
            {"$match": {"tcg": "pokemon"}},
            {"$group": {"_id": "$set.id", "name": {"$first": "$set.name"}, "rd": {"$first": "$set.release_date"},
                        "pt": {"$first": "$set.printed_total"}}}]):
        rd = d.get("rd")
        year = rd.year if hasattr(rd, "year") else (int(str(rd)[:4]) if rd else None)
        out.append({"id": d["_id"], "name": d.get("name"), "year": year, "printed_total": d.get("pt"),
                    "toks": set(words(d.get("name"))) - SET_NOISE})
    _sets_cache = (now(), out)
    return out


def _w(tok: str) -> float:
    return 0.5 if tok in GENERIC_SET else 1.0


async def resolve_sets(db, info: CertInfo) -> list[str]:
    """Catalog set ids the page's set string + year point at, best first (at most 3). Page words like 'Pokemon',
    'EN-', languages are dropped on both sides; series words ('Scarlet and Violet') count half; the release year is
    a bonus. 'Paldean Fates' beats 'Scarlet & Violet' for '2024 Pokemon Scarlet and Violet Paldean Fates'."""
    page = set(words(info.set_name)) - SET_NOISE
    if not page:
        return []
    ranked = []
    for s in await _sets(db):
        have = s["toks"]
        if not have:
            continue
        hit = have & page
        matched = sum(_w(t) for t in hit)
        q = matched / sum(_w(t) for t in have)
        year_ok = bool(info.year and s["year"] == info.year)
        if q < 0.6 or (matched < 1 and not year_ok) or (len(have) > 1 and len(hit) < 2):
            continue  # a lone series word ('Base', 'Scarlet') only counts together with the release year
        bonus = 1.0 if year_ok else 0.0
        if info.printed_total and s["printed_total"] == info.printed_total:
            bonus += 0.5
        ranked.append(((matched + bonus) * q, s["id"]))
    ranked.sort(key=lambda r: -r[0])
    return [i for sc, i in ranked if ranked and sc >= ranked[0][0] * 0.75][:3]


def name_hits(info: CertInfo, pool: list[dict]) -> dict[str, bool]:
    """Catalog cards (id -> exact?) whose name words all sit inside the page name words; only the longest catalog
    names are kept ('gardevoir ex' wins over 'gardevoir'). Exact = the page has no other word besides noise."""
    page = set(words(info.name))
    if not page:
        return {}
    hit = [(c, set(words(c.get("name")))) for c in pool]
    hit = [(c, w) for c, w in hit if w and w <= page]
    if not hit:
        return {}
    top = max(len(w) for _, w in hit)
    return {c["_id"]: not (page - w - NOISE) for c, w in hit if len(w) == top}


def signals(info: CertInfo, card: dict, name_hit: bool | None, set_ids: list[str] = ()) -> list[str]:
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
    if s.get("id") in set_ids:
        sig.append("set")
    rd = s.get("release_date")
    year = rd.year if hasattr(rd, "year") else (int(str(rd)[:4]) if rd else None)
    if info.year and year == info.year:
        sig.append("year")
    want = page_rarity(info.name, info.variant)
    if want and card.get("rarity") and frozenset(words(card["rarity"])) == want:
        sig.append("rarity")
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


async def _global_pool(db, info: CertInfo) -> list[dict]:
    """Name-only candidates when the set is unknown or has no hit: catalog cards sharing a distinctive page word."""
    toks = [t for t in dict.fromkeys(words(info.name)) if len(t) >= 3 and t not in NOISE]
    if not toks:
        return []
    rx = "|".join("'?".join(re.escape(ch) for ch in t) for t in toks)  # the catalog keeps apostrophes: farfetch'd
    return [c async for c in db.cards.find({"tcg": "pokemon", "name_norm": {"$regex": rf"\b(?:{rx})\b"}},
                                           {"raw": 0}).limit(POOL * 3)]


async def match_catalog(db, info: CertInfo) -> list[dict]:
    """Catalog prints for a found cert, best first, each with `signals` and `match_label`. Set first (page set
    string -> catalog sets, then name words inside them), global name match as the fallback."""
    from app.services import scan
    set_ids = await resolve_sets(db, info)
    hits: dict[str, bool] = {}
    pool: list[dict] = []
    if set_ids:
        pool = [c async for c in db.cards.find({"tcg": "pokemon", "set.id": {"$in": set_ids}}, {"raw": 0})]
        hits = name_hits(info, pool)
    if not hits:
        pool = await _global_pool(db, info)
        hits = name_hits(info, pool)
    found = [c for c in pool if c["_id"] in hits]
    if not found and info.number and info.printed_total:
        found = [c async for c in db.cards.find(
            {"tcg": "pokemon", "set.printed_total": info.printed_total,
             "number": {"$in": scan._number_forms(info.number.split("/")[0])}}, {"raw": 0}).limit(MAX_CARDS)]
    sigs = {c["_id"]: signals(info, c, hits.get(c["_id"]), set_ids) for c in found}
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


# Digits a real cert has per grader (tighter than the registry's loose lookup range): outside = probably misread.
CERT_DIGITS = {"ACE": (5, 7), "PSA": (8, 9), "BGS": (10, 10)}


def _tier(t: str | None) -> str:
    return " ".join("mint" if w == "mt" else w for w in words(t))


def warnings(info: CertInfo, cards: list[dict], label_grade: float | None = None, label_tier: str | None = None) -> list[dict]:
    """Tripwires for a cert that was probably misread: the page does not agree with the label, or is not a Pokémon
    card. Each is `{code, text}`; the UI says 'check the cert digits'. Never blocks anything."""
    out: list[dict] = []
    lo_hi = CERT_DIGITS.get(info.grader)
    if lo_hi and not lo_hi[0] <= len(info.cert or "") <= lo_hi[1]:
        want = f"{lo_hi[0]}" if lo_hi[0] == lo_hi[1] else f"{lo_hi[0]}-{lo_hi[1]}"
        out.append({"code": "cert_length", "text": f"{info.grader} certs have {want} digits, this one has {len(info.cert or '')}"})
    if info.status != FOUND:
        return out
    if label_grade is not None and info.grade is not None and abs(label_grade - info.grade) > 0.01:
        out.append({"code": "grade_mismatch", "text": f"label says {label_grade:g}, page says {info.grade:g}"})
    if label_tier and info.tier and _tier(label_tier) != _tier(info.tier):
        out.append({"code": "tier_mismatch", "text": f"label says {label_tier}, page says {info.tier}"})
    seen = " ".join(words(" ".join(x for x in (info.set_name, info.name, info.variant, info.language) if x)))
    if not cards and "pokemon" not in seen:
        out.append({"code": "not_pokemon", "text": f"the page is not a Pokemon card ({info.name or '?'}, {info.set_name or '?'})"})
    return out


async def lookup(db, grader: str, cert: str, client: FetcherClient | None = None, transport=None,
                 refresh: bool = False, label_grade: float | None = None, label_tier: str | None = None) -> dict:
    """`{cert: CertInfo doc, cards, how_exact, needs_confirm, cached, warnings}`; the cards are only listed for a
    found cert. The label grade / tier (when the caller read them) are compared with the page for `warnings`."""
    info, cached = await fetch_info(db, grader, cert, client, transport, refresh)
    cards = await match_catalog(db, info) if info.status == FOUND else []
    level = how_exact(info.grader, cards)
    return {"cert": info.to_doc(), "cards": cards, "how_exact": level, "cached": cached,
            "needs_confirm": level != "none" and (level != "exact" or info.grader in CONFIRM_ALWAYS),
            "report_url": info.url, "warnings": warnings(info, cards, label_grade, label_tier)}


async def recent(db, limit: int = 20) -> list[dict]:
    """Last cert lookups with how the catalog matched them, so a bad scan can be inspected without a Mongo shell."""
    out = []
    async for d in db.cert_cache.find({}).sort("fetched_at", -1).limit(limit):
        info = CertInfo.from_doc(d["info"])
        row = {"grader": d.get("grader"), "cert": d.get("cert"), "status": d.get("status"), "lookups": d.get("lookups"),
               "fetched_at": d.get("fetched_at"), "name": info.name, "set_name": info.set_name, "number": info.number,
               "year": info.year, "grade": info.grade, "match": None}
        if info.status == FOUND:
            cards = await match_catalog(db, info)
            row["match"] = {"how_exact": how_exact(info.grader, cards), "sets": await resolve_sets(db, info),
                            "top": [{"id": c["id"], "name": c["name"], "number": c.get("number"),
                                     "set": (c.get("set") or {}).get("name"), "signals": c["signals"]}
                                    for c in cards[:3]],
                            "warnings": warnings(info, cards)}
        out.append(row)
    return out


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
