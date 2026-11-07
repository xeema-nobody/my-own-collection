"""Phone scanning: read a card name from a photo, list every plausible version, add the chosen one.

Never auto-adds: `identify` only proposes cards, `add_scanned` runs when the user taps one."""
import asyncio
import dataclasses
import difflib
import logging
import re
import time
from datetime import datetime, timedelta, timezone

from bson import ObjectId

from app.api.deps import clean
from app.db.models import CollectionIn
from app.providers.catalog.common import norm
from app.providers.ocr import CardFields, ImageError, OcrLine, OcrUnavailable
from app.services import collection as collection_svc
from app.services import valuation_cache
from app.services.search import build_query, find_page

log = logging.getLogger(__name__)
MAX_CARDS = 40
POOL = 400  # prints scored before the best MAX_CARDS are returned
NUMBER_ONLY_MAX = 12  # prints offered when only number + printed total were read
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


def _num(n: str | None) -> str:
    return (n or "").strip().lower().lstrip("0")


def _digits(n: str | None) -> str:
    return re.sub(r"\D", "", n or "").lstrip("0")


def signals_for(c: dict, fields: CardFields | None, name_hit: bool, codes: set[str]) -> list[str]:
    """Which of the read signals this print agrees with, in the order shown to the user."""
    sig = ["name"] if name_hit else []
    if not fields:
        return sig
    s = c.get("set") or {}
    if fields.number and (_num(c.get("number")) == _num(fields.number)
                          or (_digits(c.get("number")) and _digits(c.get("number")) == _digits(fields.number))):
        sig.append("number")
    if fields.printed_total and s.get("printed_total") == fields.printed_total:
        sig.append("total")
    code = (fields.set_code or "").lower()
    if code and code in codes and (s.get("ptcgo_code") or "").lower() == code:
        sig.append("set")
    if fields.hp and str(c.get("hp") or "").strip() == str(fields.hp):
        sig.append("hp")
    return sig


SIGNAL_TEXT = {"name": "name", "number": "number", "total": "printed total", "set": "set code", "hp": "HP"}
# How much each agreeing signal counts when ranking prints. The collector number is the strongest read, the printed
# total and set code say which set, HP only separates prints of one name (and the ex / non-ex forms).
WEIGHT = {"name": 1.0, "number": 4.0, "total": 3.0, "set": 3.0, "hp": 1.0}


def score(sig: list[str]) -> float:
    return sum(WEIGHT[x] for x in sig)


async def trusted(db, fields: CardFields | None) -> CardFields | None:
    """The read without its printed total when no catalog card carries that number / total pair: the total is the
    weaker read ("137/412" for 137/128) and a wrong one would rank another set's print first. The number stays."""
    if not fields or not fields.number:
        return fields
    if not fields.printed_total:
        return fields
    hit = await db.cards.find_one({"tcg": "pokemon", "set.printed_total": fields.printed_total,
                                   "number": {"$in": _number_forms(fields.number)}}, {"_id": 1})
    if hit:
        return fields
    return dataclasses.replace(fields, printed_total=None)


def label_for(sig: list[str]) -> str | None:
    return (" + ".join(SIGNAL_TEXT[x] for x in sig) + " match") if sig else None


async def set_codes(db) -> set[str]:
    return {c.lower() for c in await db.cards.distinct("set.ptcgo_code", {"tcg": "pokemon"}) if c}


async def read_fields(ocr, image: bytes) -> CardFields | None:
    """Number / set / HP from the flat card; never fatal, the name alone still works."""
    if not hasattr(ocr, "read_fields"):
        return None
    try:
        return await ocr.read_fields(image)
    except (OcrUnavailable, ImageError):
        log.warning("card fields unreadable", exc_info=True)
        return None


def read_view(f: CardFields | None) -> dict | None:
    if not f:
        return None
    return {"number": f.number, "printed_total": f.printed_total, "set_code": f.set_code, "hp": f.hp}


async def read_slab(ocr, image: bytes) -> dict | None:
    """Grader / grade / cert from a graded-card label, or None (not a slab, or the reader is missing). Never fatal."""
    if not hasattr(ocr, "read_slab"):
        return None
    try:
        got = await ocr.read_slab(image)
    except (OcrUnavailable, ImageError):
        log.warning("slab label unreadable", exc_info=True)
        return None
    return got.as_dict() if got else None


async def identify(db, ocr, image: bytes, slab: bool = False) -> dict:
    """Card candidates from the photo; `slab` (slab mode) always reads the label, in parallel. In raw mode the label is
    only read when the card itself was not an exact hit, so a bare raw card stays fast; a label found there sets
    `detected` so the UI can offer to switch to slab mode (never switches silently)."""
    if slab:
        res, label = await asyncio.gather(identify_card(db, ocr, image), read_slab(ocr, image))
    else:
        res = await identify_card(db, ocr, image)
        label = None if res["exact"] else await read_slab(ocr, image)
    res["slab"] = label
    res["detected"] = bool(label) and not slab
    return res


async def identify_card(db, ocr, image: bytes) -> dict:
    # the name stages and the number/set reads are independent: run them side by side (separate tesseract processes)
    (lines, matches), fields = await asyncio.gather(read_until_match(db, ocr, image), read_fields(ocr, image))
    text = " | ".join(ln.text for ln in lines)
    keep = [m for m in matches if m[1] >= matches[0][1] - 0.08][:3] if matches else []
    keep += with_suffix_variants(await card_names(db), keep)
    read = fields
    fields = await trusted(db, fields)
    codes = await set_codes(db) if fields and fields.set_code else set()
    rank = {n: i for i, (n, _) in enumerate(keep)}
    stamp = lambda c: str((c.get("set") or {}).get("release_date") or "")  # noqa: E731
    if keep:
        found = [c async for c in db.cards.find({"tcg": "pokemon", "name_norm": {"$in": list(rank)}}, {"raw": 0})
                 .limit(POOL)]
        found.sort(key=stamp, reverse=True)  # newest set first ...
        found.sort(key=lambda c: rank[c["name_norm"]])  # ... best name first (stable)
        sigs = {c["_id"]: signals_for(c, fields, True, codes) for c in found}
    elif fields and fields.number and fields.printed_total:
        # No readable name: number + printed total alone still narrow the catalog to a handful of prints.
        found = [c async for c in db.cards.find(
            {"tcg": "pokemon", "set.printed_total": fields.printed_total, "number": {"$in": _number_forms(fields.number)}},
            {"raw": 0}).limit(NUMBER_ONLY_MAX)]
        found.sort(key=stamp, reverse=True)
        sigs = {c["_id"]: signals_for(c, fields, False, codes) for c in found}
    else:
        found, sigs = [], {}
    # Most agreeing signals first; the stable sort keeps best name, then newest set, inside a tie.
    found.sort(key=lambda c: -score(sigs[c["_id"]]))
    total = len(found)
    top = found[:MAX_CARDS]
    cards = await views(db, top)
    for c, v in zip(top, cards):
        v["signals"] = sigs[c["_id"]]
        v["match_label"] = label_for(v["signals"])
    cards.sort(key=lambda v: (-score(v["signals"]), rank.get(norm(v["name"]), 0), -v["owned_qty"]))
    best = score(cards[0]["signals"]) if cards else 0
    exact = bool(cards) and len(cards[0]["signals"]) >= 2 and (
        "number" in cards[0]["signals"] or "set" in cards[0]["signals"]) and (
        len(cards) == 1 or score(cards[1]["signals"]) < best)
    names = [n for n, _ in keep]
    conf = confidence(matches, lines) if keep else ("low" if cards else "none")
    return {"text": text, "confidence": conf, "names": names, "total": total, "cards": cards,
            "read": read_view(read), "exact": exact}


def _number_forms(n: str) -> list[str]:
    """Stored numbers keep their printed form ("4", "004"); try the unpadded and padded spellings."""
    bare = n.lstrip("0") or "0"
    return [bare, bare.zfill(2), bare.zfill(3), n]


def parse_number(raw: str) -> tuple[str, int | None]:
    """"127/182" -> ("127", 182); "TG05/TG30" -> ("TG05", None); "127" -> ("127", None)."""
    left, _, right = raw.strip().partition("/")
    total = int(re.sub(r"\D", "", right)) if re.sub(r"\D", "", right) and right.strip().isdigit() else None
    return left.strip(), total


async def lookup(db, number: str, set_q: str | None = None) -> dict:
    """Typed fallback for an unreadable photo: collector number (+ printed total) and an optional set code, set
    id or part of the set name. Same answer shape as `identify` so the picker is reused."""
    num, total = parse_number(number)
    if not num:
        return {"text": "", "confidence": "none", "names": [], "total": 0, "cards": [], "read": None, "exact": False}
    flt: dict = {"tcg": "pokemon", "number": {"$in": _number_forms(num) + [num.upper()]}}
    if total:
        flt["set.printed_total"] = total
    q = (set_q or "").strip()
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        flt["$or"] = [{"set.ptcgo_code": {"$regex": f"^{re.escape(q)}$", "$options": "i"}},
                      {"set.id": q.lower()}, {"set.name": rx}]
    found = [c async for c in db.cards.find(flt, {"raw": 0}).limit(POOL)]
    found.sort(key=lambda c: str((c.get("set") or {}).get("release_date") or ""), reverse=True)
    sigs = {}
    for c in found:
        sg = ["number"]
        if total:
            sg.append("total")
        if q:
            sg.append("set")
        sigs[c["_id"]] = sg
    top = found[:MAX_CARDS]
    cards = await views(db, top)
    for c, v in zip(top, cards):
        v["signals"] = sigs[c["_id"]]
        v["match_label"] = label_for(v["signals"])
    exact = len(cards) == 1
    return {"text": "", "confidence": "high" if exact else ("medium" if cards else "none"), "names": [],
            "total": len(found), "cards": cards, "read": {"number": num, "printed_total": total, "set_code": q or None,
                                                          "hp": None}, "exact": exact}


async def search(db, q: str, page: int = 1, page_size: int = 24) -> dict:
    flt = build_query(q, tcg="pokemon")
    total = await db.cards.count_documents(flt)
    found = await find_page(db, flt, "release", (page - 1) * page_size, page_size)
    return {"total": total, "page": page, "cards": await views(db, found)}


SESSION_IDLE_MIN = 30  # an open session with no activity for this long is treated as closed
UNDO_WINDOW_MIN = 10


class ScanError(Exception):
    """Business-rule failure; `status` is the HTTP code the router answers with."""
    def __init__(self, status: int, msg: str):
        super().__init__(msg)
        self.status = status


def _session_out(s: dict | None) -> dict | None:
    return None if not s else {"id": str(s["_id"]), "created_at": s["created_at"].isoformat()}


async def start_session(db) -> dict:
    """Laptop opens a session; any older open one is closed (one at a time)."""
    now = datetime.now(timezone.utc)
    await db.scan_sessions.update_many({"status": "open"}, {"$set": {"status": "closed", "closed_at": now}})
    res = await db.scan_sessions.insert_one({"status": "open", "created_at": now, "last_activity": now})
    return _session_out({"_id": res.inserted_id, "created_at": now})


async def current_session(db) -> dict | None:
    """The open, not idle-expired session (what the phone polls), or None."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=SESSION_IDLE_MIN)
    s = await db.scan_sessions.find_one({"status": "open", "last_activity": {"$gte": cutoff}}, sort=[("_id", -1)])
    return _session_out(s)


async def close_session(db, session_id: str) -> bool:
    try:
        oid = ObjectId(session_id)
    except Exception:
        return False
    r = await db.scan_sessions.update_one({"_id": oid, "status": "open"},
                                          {"$set": {"status": "closed", "closed_at": datetime.now(timezone.utc)}})
    return bool(r.matched_count)


async def add_scanned(db, body: CollectionIn, session_id: str | None = None) -> dict:
    """Add through the normal stack merge, then log it for the laptop's "added: ..." toast."""
    key = collection_svc.stack_key(body)
    before = await db.collection_items.find_one({"stack_key": key}, {"acquired": 1})
    if body.grading and body.grading.company == "OTHER" and not body.grading.grader_name:
        raise ScanError(422, "type the grader's name for an Other slab")
    stack = await collection_svc.add(db, body)
    added = 0 if stack.get("duplicate") else body.quantity
    card = await db.cards.find_one({"_id": body.card_id}, {"name": 1, "set.name": 1, "number": 1})
    label = f"{card['name']}, {(card.get('set') or {}).get('name', '?')}"
    if body.grading:
        g = body.grading
        label += f" ({(g.grader_name or 'Other') if g.company == 'OTHER' else g.company} {g.grade:g})"
    now = datetime.now(timezone.utc)
    ev = {"at": now, "kind": "add", "card_id": body.card_id, "label": label, "stack_id": stack["id"],
          "quantity_added": added, "quantity_after": stack["quantity"],
          "type_conflict": bool(stack.get("type_conflict")), "condition": body.condition,
          "grading": body.grading.model_dump() if body.grading else None, "language": body.language,
          "session_id": session_id, "existed": before is not None,
          "prev_acquired": before.get("acquired") if before else None}
    res = await db.scan_events.insert_one(ev)
    if session_id:
        try:
            await db.scan_sessions.update_one({"_id": ObjectId(session_id), "status": "open"}, {"$set": {"last_activity": now}})
        except Exception:
            pass
    return {"stack": stack, "event": _event_out({**ev, "_id": res.inserted_id}), "label": label}


async def undo(db, event_id: str) -> dict:
    """Take back the most recent scanned add (only that one, only within UNDO_WINDOW_MIN). Quantity goes down by
    what the add put in; the stack is deleted when that empties it (a mistaken add, so no exit row)."""
    try:
        oid = ObjectId(event_id)
    except Exception:
        raise ScanError(404, "nothing to undo")
    ev = await db.scan_events.find_one({"_id": oid, "kind": {"$in": ["add", None]}})
    if not ev:
        raise ScanError(404, "nothing to undo")
    if ev.get("quantity_added") == 0:
        raise ScanError(409, "that slab was already in the collection, nothing was added")
    if ev.get("undone"):
        raise ScanError(409, "already undone")
    at = ev["at"] if ev["at"].tzinfo else ev["at"].replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - at > timedelta(minutes=UNDO_WINDOW_MIN):
        raise ScanError(409, "too late to undo, fix it on the laptop")
    if await db.scan_events.find_one({"_id": {"$gt": oid}, "kind": {"$in": ["add", None]}, "undone": {"$ne": True}}):
        raise ScanError(409, "only the last card can be undone")
    stack = await db.collection_items.find_one({"_id": ObjectId(ev["stack_id"])})
    if not stack or stack["quantity"] < ev["quantity_added"]:
        raise ScanError(409, "that stack changed on the laptop, fix it there")
    left = stack["quantity"] - ev["quantity_added"]
    try:
        if left <= 0:
            await db.collection_items.delete_one({"_id": stack["_id"]})
        else:
            fields = {"quantity": left, "updated_at": datetime.now(timezone.utc)}
            if ev.get("existed"):
                fields["acquired"] = ev.get("prev_acquired")  # undo the weighted-average cost merge too
            await db.collection_items.update_one({"_id": stack["_id"]}, {"$set": fields})
    finally:
        valuation_cache.bump()
    await db.scan_events.update_one({"_id": oid}, {"$set": {"undone": True}})
    res = await db.scan_events.insert_one({
        "at": datetime.now(timezone.utc), "kind": "undo", "card_id": ev["card_id"], "label": ev["label"],
        "stack_id": ev["stack_id"], "quantity_added": ev["quantity_added"], "quantity_after": max(left, 0),
        "type_conflict": False, "session_id": ev.get("session_id"), "undoes": event_id})
    return {"label": ev["label"], "quantity": max(left, 0), "deleted": left <= 0, "event_id": str(res.inserted_id)}


def _event_out(e: dict) -> dict:
    return {"id": str(e["_id"]), "at": e["at"].isoformat(), "kind": e.get("kind") or "add", "card_id": e["card_id"],
            "label": e["label"], "quantity_added": e["quantity_added"], "quantity_after": e["quantity_after"],
            "type_conflict": e.get("type_conflict", False), "condition": e.get("condition"),
            "grading": e.get("grading"), "language": e.get("language"), "session_id": e.get("session_id"),
            "undoes": e.get("undoes")}


async def events_after(db, after: str | None, session_id: str | None = None) -> dict:
    """Events newer than `after`. Without it only the cursor is returned, so a fresh page shows no history."""
    if after is None:
        last = await db.scan_events.find_one(sort=[("_id", -1)])
        return {"events": [], "latest": str(last["_id"]) if last else None}
    try:
        q: dict = {"_id": {"$gt": ObjectId(after)}}
        if session_id:
            q["session_id"] = session_id
        cur = db.scan_events.find(q).sort("_id", 1).limit(50)
    except Exception:
        return {"events": [], "latest": None}
    evs = [_event_out(e) async for e in cur]
    return {"events": evs, "latest": evs[-1]["id"] if evs else after}
