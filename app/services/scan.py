"""Phone scanning: read a card name from a photo, list every plausible version, add the chosen one.

Never auto-adds: `identify` only proposes cards, `add_scanned` runs when the user taps one."""
import difflib
import re
import time
from datetime import datetime, timezone

from bson import ObjectId

from app.api.deps import clean
from app.db.models import CollectionIn
from app.providers.catalog.common import norm
from app.providers.ocr import OcrLine
from app.services import collection as collection_svc
from app.services.search import build_query, find_page

MAX_CARDS = 40
NAME_TTL_S = 600
CLOSE_CUTOFF = 0.75
EVOLVES = re.compile(r"volve|elves|\bfrom\b")  # tolerant of a half-read "Evolves from"
NAME_WINDOW = 4  # longest run of words tried as a name
# Words printed beside the name that are not part of it.
NOISE = {"basic", "stage", "hp", "evolves", "from", "lv", "tera", "restored", "ability", "pokemon"}
# Sets with 1st Edition (and for base1 Shadowless) prints the catalog does not list as separate cards.
EDITION_SETS = {
    "base1": "1st Edition / Shadowless / Unlimited", "base2": "1st Edition / Unlimited",
    "base3": "1st Edition / Unlimited", "base5": "1st Edition / Unlimited", "gym1": "1st Edition / Unlimited",
    "gym2": "1st Edition / Unlimited", "neo1": "1st Edition / Unlimited", "neo2": "1st Edition / Unlimited",
    "neo3": "1st Edition / Unlimited", "neo4": "1st Edition / Unlimited",
}

_names: tuple[float, list[str]] | None = None


async def card_names(db) -> list[str]:
    """Distinct normalised card names (cached; the catalog changes at most weekly)."""
    global _names
    if _names is None or time.monotonic() - _names[0] > NAME_TTL_S:
        _names = (time.monotonic(), sorted(await db.cards.distinct("name_norm", {"tcg": "pokemon"})))
    return _names[1]


def reset_names_cache() -> None:
    global _names
    _names = None


def windows(lines: list[OcrLine]) -> list[tuple[str, float]]:
    """Candidate name strings with the confidence of their line, longest runs of words first."""
    out: dict[str, float] = {}
    for ln in lines:
        text = EVOLVES.split(norm(ln.text))[0]  # "Evolves from X" names the previous stage, not this card
        words = [w for w in re.findall(r"[a-z][a-z'.\-]*", text) if w not in NOISE]
        for n in range(min(NAME_WINDOW, len(words)), 0, -1):
            for i in range(len(words) - n + 1):
                w = " ".join(words[i:i + n])
                if len(w) >= 3:
                    out[w] = max(out.get(w, 0), ln.conf)
    return sorted(out.items(), key=lambda kv: (-len(kv[0].split()), -kv[1]))


def match_names(names: list[str], cands: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """(name, score 0-1) best first. Exact windows win; fuzzy only when nothing matched exactly."""
    known = set(names)
    scores: dict[str, float] = {}
    for w, _ in cands:
        if w in known:
            scores[w] = 1.0
    if not scores:
        for w, _ in cands[:8]:
            for m in difflib.get_close_matches(w, names, n=3, cutoff=CLOSE_CUTOFF):
                scores[m] = max(scores.get(m, 0), difflib.SequenceMatcher(None, w, m).ratio())
    return sorted(scores.items(), key=lambda kv: (-kv[1], -len(kv[0])))


VARIANT = re.compile(r"^(?:ex|v|vmax|vstar|gx|break|star)$")


def with_suffix_variants(names: list[str], keep: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """The printed "ex"/"V" glyph is rarely read, so a matched base name also brings its ex/V/GX forms."""
    have = {n for n, _ in keep}
    out = []
    for n, sc in keep:
        for other in names:
            base, _, tail = other.rpartition(" ")
            if base == n and VARIANT.match(tail) and other not in have:
                out.append((other, sc))
                have.add(other)
    return out


def confidence(matches: list[tuple[str, float]], lines: list[OcrLine]) -> str:
    if not matches:
        return "none"
    best = max((ln.conf for ln in lines), default=0)
    if matches[0][1] >= 1.0 and best >= 60:
        return "high"
    return "medium" if matches[0][1] >= 0.85 else "low"


def card_view(c: dict, owned: list[dict]) -> dict:
    c = clean(c)
    s = c.get("set") or {}
    year = (s.get("release_date") or "")[:4] if isinstance(s.get("release_date"), str) else (
        s["release_date"].year if s.get("release_date") else None)
    return {
        "id": c["id"], "name": c["name"], "number": c.get("number"), "printed_total": s.get("printed_total"),
        "set": {"id": s.get("id"), "name": s.get("name")}, "year": int(year) if year else None,
        "rarity": c.get("rarity"), "image": (c.get("images") or {}).get("small"), "variants": c.get("variants") or [],
        "price": c.get("price_base"), "language": c.get("language", "en"),
        "edition_note": EDITION_SETS.get(s.get("id") or ""),
        "owned_qty": sum(o["quantity"] for o in owned),
        "owned": [{"condition": o.get("condition"), "language": o.get("language"), "variant": o.get("variant"),
                   "grading": o.get("grading"), "quantity": o["quantity"]} for o in owned],
    }


async def views(db, cards: list[dict]) -> list[dict]:
    owned: dict[str, list[dict]] = {}
    async for o in db.collection_items.find({"card_id": {"$in": [c["_id"] for c in cards]}}):
        owned.setdefault(o["card_id"], []).append(o)
    return [card_view(c, owned.get(c["_id"], [])) for c in cards]


STOP_CONF = 55  # an exact name found on a line at least this sure ends the staged read early


async def read_until_match(db, ocr, image: bytes) -> tuple[list[OcrLine], list[tuple[str, float]]]:
    """Run the reader stage by stage (cheap crops first), stop at the first confident exact name."""
    names = await card_names(db)
    known = set(names)
    if hasattr(ocr, "stages"):
        batches = ocr.stages(image)
    else:
        async def one():
            yield await ocr.read_lines(image)
        batches = one()
    lines: list[OcrLine] = []
    async for batch in batches:
        lines += batch
        if any(w in known and c >= STOP_CONF and len(w) >= 4 for w, c in windows(batch)):
            break
    return lines, match_names(names, windows(lines))


async def identify(db, ocr, image: bytes) -> dict:
    lines, matches = await read_until_match(db, ocr, image)
    text = " | ".join(ln.text for ln in lines)
    keep = [m for m in matches if m[1] >= matches[0][1] - 0.08][:3] if matches else []
    keep += with_suffix_variants(await card_names(db), keep)
    cards: list[dict] = []
    if keep:
        rank = {n: i for i, (n, _) in enumerate(keep)}
        found = [c async for c in db.cards.find({"tcg": "pokemon", "name_norm": {"$in": list(rank)}}, {"raw": 0})]
        stamp = lambda c: str((c.get("set") or {}).get("release_date") or "")  # noqa: E731
        found.sort(key=stamp, reverse=True)  # newest set first ...
        found.sort(key=lambda c: rank[c["name_norm"]])  # ... best name first (stable)
        total = len(found)
        cards = await views(db, found[:MAX_CARDS])
        cards.sort(key=lambda v: (rank[norm(v["name"])], -v["owned_qty"] if v["owned_qty"] else 0))
    else:
        total = 0
    return {"text": text, "confidence": confidence(matches, lines), "names": [n for n, _ in keep],
            "total": total, "cards": cards}


async def search(db, q: str, page: int = 1, page_size: int = 24) -> dict:
    flt = build_query(q, tcg="pokemon")
    total = await db.cards.count_documents(flt)
    found = await find_page(db, flt, "release", (page - 1) * page_size, page_size)
    return {"total": total, "page": page, "cards": await views(db, found)}


async def add_scanned(db, body: CollectionIn) -> dict:
    """Add through the normal stack merge, then log it for the laptop's "added: ..." toast."""
    stack = await collection_svc.add(db, body)
    card = await db.cards.find_one({"_id": body.card_id}, {"name": 1, "set.name": 1, "number": 1})
    label = f"{card['name']}, {(card.get('set') or {}).get('name', '?')}"
    ev = {"at": datetime.now(timezone.utc), "card_id": body.card_id, "label": label, "stack_id": stack["id"],
          "quantity_added": body.quantity, "quantity_after": stack["quantity"],
          "type_conflict": bool(stack.get("type_conflict"))}
    res = await db.scan_events.insert_one(ev)
    return {"stack": stack, "event": _event_out({**ev, "_id": res.inserted_id}), "label": label}


def _event_out(e: dict) -> dict:
    return {"id": str(e["_id"]), "at": e["at"].isoformat(), "card_id": e["card_id"], "label": e["label"],
            "quantity_added": e["quantity_added"], "quantity_after": e["quantity_after"],
            "type_conflict": e.get("type_conflict", False)}


async def events_after(db, after: str | None) -> dict:
    """Events newer than `after`. Without it only the cursor is returned, so a fresh page shows no history."""
    if after is None:
        last = await db.scan_events.find_one(sort=[("_id", -1)])
        return {"events": [], "latest": str(last["_id"]) if last else None}
    try:
        cur = db.scan_events.find({"_id": {"$gt": ObjectId(after)}}).sort("_id", 1).limit(50)
    except Exception:
        return {"events": [], "latest": None}
    evs = [_event_out(e) async for e in cur]
    return {"events": evs, "latest": evs[-1]["id"] if evs else after}
