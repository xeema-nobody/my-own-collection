"""Listing pack (roadmap 6c): per stack a ready title / description / price / photo list for Vinted, and a
Cardmarket stock sheet. Nothing is published or marked here; marking Listed goes through `sale.set_sale`.
Money is integer cents; a stack without a price gets `price None` + a warning, never 0."""
import csv
import io
import zipfile
from bson import ObjectId

from app.services import collection as svc, photos as photos_svc

VINTED_TITLE_MAX = 100  # Vinted's own limits; truncation is reported as a warning
VINTED_DESC_MAX = 2000
STRATEGIES = ("market", "under", "floor")
LANG = {"en": "English", "ja": "Japanese", "es": "Spanish", "it": "Italian", "fr": "French", "de": "German",
        "pt": "Portuguese", "ko": "Korean", "zh": "Chinese"}
COND = {"NM": "Near Mint", "LP": "Lightly Played", "MP": "Moderately Played", "HP": "Heavily Played", "DMG": "Damaged"}
# Cardmarket grades: MT NM EX GD LP PL PO. Assumed mapping from our five levels (see decisions.md).
CM_COND = {"NM": "NM", "LP": "EX", "MP": "GD", "HP": "LP", "DMG": "PL"}
# Vinted mapping decided with the user 2026-11-11 (docs/vinted-sell-flow.md); editable per row in the Publish table.
VINTED_COND = {"raw": "Very good", "slab": "New without tags"}
VINTED_PARCEL = {"raw": "small", "slab": "medium"}
CM_COLUMNS = ["name", "set", "number", "language", "condition", "quantity", "price", "comment"]


def _grade_text(g: dict) -> str:
    company = g.get("grader_name") if g["company"] == "OTHER" else g["company"]
    grade = g["grade"]
    return f"{company or 'Other'} {int(grade) if float(grade).is_integer() else grade}"


def _cut(text: str, limit: int, what: str, warnings: list[str]) -> str:
    if len(text) <= limit:
        return text
    warnings.append(f"{what} cut to {limit} characters")
    return text[:limit - 1].rstrip() + "…"


def price_for(row: dict, strategy: str, pct: int) -> int | None:
    """Asking price per copy in base-currency cents, or None when the stack has no price."""
    qty = row["item"]["quantity"]
    if row["value"] is None:
        return None
    if strategy == "floor":
        lo = (row.get("spread") or {}).get("min")
        base = lo if lo is not None else row["value"]
    elif strategy == "under":
        base = row["value"] * (100 - pct) / 100
    else:
        base = row["value"]
    return max(1, round(base / qty))


def _text(row: dict) -> tuple[str, str]:
    it, c = row["item"], row["card"] or {}
    g = it.get("grading")
    lines = [f"{c.get('name', 'Card')} - {(c.get('set') or {}).get('name', '')} #{c.get('number', '')}".replace(" - #", " #")]
    if c.get("rarity"):
        lines.append(f"Rarity: {c['rarity']}")
    if it.get("variant"):
        lines.append(f"Variant: {it['variant']}")
    lines.append(f"Language: {LANG.get(it.get('language', 'en'), it.get('language'))}")
    if g:
        lines.append(f"Graded: {_grade_text(g)}" + (f", cert {g['cert_number']}" if g.get("cert_number") else ""))
        if g.get("report_url"):
            lines.append(f"Report: {g['report_url']}")
    else:
        lines.append(f"Condition: {COND.get(it.get('condition'), it.get('condition'))}")
    if it["quantity"] > 1 and not g:
        lines.append(f"Quantity available: {it['quantity']}")
    lines.append("Sent in a sleeve and toploader. Photos show the actual card.")
    title_bits = [c.get("name", "Card"), f"{(c.get('set') or {}).get('name', '')} {c.get('number', '')}".strip(),
                  _grade_text(g) if g else COND.get(it.get("condition"), "")]
    if it.get("language", "en") != "en":
        title_bits.append(LANG.get(it["language"], it["language"]))
    return " - ".join(b for b in title_bits if b), "\n".join(lines)


async def _photo_ids(db, stack_id: str) -> list[str]:
    ps = await photos_svc.list_for_stack(db, stack_id)
    ps.sort(key=lambda p: (not p["cover"], p["order"]))  # cover first
    return [p["id"] for p in ps]


async def _stored_vinted(db, stack_id: str, item: dict) -> dict | None:
    """What the stack was last published with on Vinted: text + mapping from the newest published queue entry, price from
    the stored Vinted listing (the user may have changed it since). None when never published or no Vinted listing."""
    listing = next((l for l in (item.get("sale") or {}).get("listings") or [] if l.get("platform") == "vinted"), None)
    last = await db.publish_queue.find_one({"item_id": stack_id, "state": "published"}, sort=[("updated_at", -1)])
    if not listing or not last:
        return None
    p = last["payload"]
    return {"title": p["title"], "description": p["description"], "condition": p["condition"], "parcel": p["parcel"],
            "price": listing["asking_price"]}


async def build_pack(db, ids: list[str], platform: str, strategy: str = "market", pct: int = 5) -> dict:
    if strategy not in STRATEGIES:
        raise ValueError(f"strategy must be one of {', '.join(STRATEGIES)}")
    oids = [svc.oid(i) for i in dict.fromkeys(ids)]
    items = await db.collection_items.find({"_id": {"$in": oids}}).to_list(None)
    found = {str(i["_id"]) for i in items}
    rows = {str(r["item"]["_id"]): r for r in await svc.valuate_items(db, items)}
    out, missing = [], [i for i in ids if i not in found]
    for sid in dict.fromkeys(ids):
        r = rows.get(sid)
        if not r:
            continue
        warnings: list[str] = []
        title, desc = _text(r)
        price = price_for(r, strategy, pct)
        if price is None:
            warnings.append("needs price: no market price for this stack")
        photos = await _photo_ids(db, sid)
        if not photos:
            warnings.append("no photos")
        if platform == "vinted":
            title = _cut(title, VINTED_TITLE_MAX, "title", warnings)
            desc = _cut(desc, VINTED_DESC_MAX, "description", warnings)
        elif r["item"].get("grading"):
            warnings.append("slab: not a Cardmarket single, left out of the sheet")
        stored = await _stored_vinted(db, sid, r["item"]) if platform == "vinted" else None
        market = price
        if stored:  # an earlier publish: its edited price / text win, the market price stays a suggestion only
            title, desc, price = stored["title"], stored["description"], stored["price"]
            warnings = [w for w in warnings if not w.startswith("needs price")]
        out.append({"item_id": sid, "card_id": r["item"]["card_id"], "title": title, "description": desc,
                    "price": price, "market_price": market, "stored": stored, "currency": "EUR", "sale": r["item"].get("sale"), "quantity": r["item"]["quantity"], "photos": photos,
                    "slab": bool(r["item"].get("grading")), "vinted_condition": (stored or {}).get("condition") or VINTED_COND["slab" if r["item"].get("grading") else "raw"],
                    "vinted_parcel": (stored or {}).get("parcel") or VINTED_PARCEL["slab" if r["item"].get("grading") else "raw"],
                    "vinted_url": next((l.get("url") for l in (r["item"].get("sale") or {}).get("listings") or []
                                        if l.get("platform") == "vinted" and l.get("url")), None),
                    "warnings": warnings})
    return {"platform": platform, "strategy": strategy, "pct": pct, "items": out, "missing": missing}


def cardmarket_csv(pack: dict, rows_by_id: dict[str, dict]) -> str:
    """Stock sheet for the pack's raw stacks. Prices in euros with 2 decimals (empty when unknown)."""
    buf = io.StringIO()
    w = csv.DictWriter(buf, CM_COLUMNS, extrasaction="ignore")
    w.writeheader()
    for p in pack["items"]:
        r = rows_by_id[p["item_id"]]
        it, c = r["item"], r["card"] or {}
        if it.get("grading"):
            continue
        w.writerow({"name": c.get("name"), "set": (c.get("set") or {}).get("name"), "number": c.get("number"),
                    "language": LANG.get(it.get("language", "en")), "condition": CM_COND.get(it.get("condition")),
                    "quantity": it["quantity"], "price": f"{p['price'] / 100:.2f}" if p["price"] is not None else "",
                    "comment": p["description"].splitlines()[1] if len(p["description"].splitlines()) > 1 else ""})
    return buf.getvalue()


async def cardmarket_sheet(db, ids: list[str], strategy: str, pct: int) -> str:
    pack = await build_pack(db, ids, "cardmarket", strategy, pct)
    items = await db.collection_items.find({"_id": {"$in": [ObjectId(i) for i in ids if ObjectId.is_valid(i)]}}).to_list(None)
    rows = {str(r["item"]["_id"]): r for r in await svc.valuate_items(db, items)}
    return cardmarket_csv(pack, rows)


async def photos_zip(db, stack_id: str) -> bytes | None:
    """Photos of one stack in listing order (cover first) as 01.jpg, 02.jpg ...; None when it has none."""
    ids = await _photo_ids(db, stack_id)
    if not ids:
        return None
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:  # JPEGs are already compressed
        for n, pid in enumerate(ids, 1):
            z.writestr(f"{n:02d}.jpg", await photos_svc.image(db, pid))
    return buf.getvalue()
