"""Reprice table + sold-comps alert for listed stacks (roadmap Step 6d, decisions.md 'Reprice').

Read-only against the marketplaces: `confirm` only changes the asking price saved in the app and flags the listing
`needs_platform_update`; the user then updates the platform (for Vinted: "Update on Vinted", which has its own confirm).
Money = integer cents; no market price = `None`, never 0."""
import logging
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from app.config import settings
from app.db.models import RepriceConfirmIn, StackSaleIn
from app.services import collection as svc
from app.services import sale
from app.services.listing_pack import price_for
from app.services.pricing import get_rates
from app.services.valuation import grade_key

log = logging.getLogger(__name__)
COMPS_PER_STACK = 5          # newest comps per stack and run: a long-listed stack never floods the inbox
DEFAULT_COMP_DAYS = 30       # listing without a listed_at date: look this far back


def suggested(market: int | None, markup_pct: int | None = None) -> int | None:
    if market is None:
        return None
    pct = settings.reprice_markup_pct if markup_pct is None else markup_pct
    return max(1, round(market * (100 + pct) / 100))


async def _listed(db) -> list[dict]:
    return await db.collection_items.find({"sale.status": "listed"}).to_list(None)


async def _last_comps(db, item: dict, rates: dict, since: datetime | None = None, limit: int = 1) -> list[dict]:
    q: dict = {"card_id": item["card_id"], "grade_key": grade_key(item)}
    if since:
        q["sold_at"] = {"$gte": since}
    out = []
    async for s in db.sales.find(q).sort("sold_at", -1).limit(limit):
        rate = rates.get(s.get("currency"))
        out.append({"id": str(s["_id"]), "price": s["price"], "currency": s.get("currency"),
                    "price_base": round(s["price"] * rate) if rate else None, "source": s.get("source"),
                    "sold_at": s["sold_at"].date().isoformat() if s.get("sold_at") else None,
                    "condition_unknown": grade_key(item) == "raw"})
    return out


def _rows_for(r: dict, comp: dict | None) -> list[dict]:
    item, card = r["item"], r["card"] or {}
    market = price_for(r, "market", 0)
    out = []
    for l in (item.get("sale") or {}).get("listings") or []:
        ask = l.get("asking_price")
        same_cur = l.get("currency") == settings.base_currency
        warnings = []
        if market is None:
            warnings.append("no market price")
        if not same_cur:
            warnings.append(f"asking price in {l.get('currency')}: no comparison")
        pct = amount = None
        if market is not None and same_cur and ask:
            amount = market - ask
            pct = round(amount / ask * 100, 1)
        out.append({"item_id": str(item["_id"]), "card_id": item["card_id"], "name": card.get("name"),
                    "set": (card.get("set") or {}).get("name"), "number": card.get("number"),
                    "grade_key": grade_key(item), "quantity": item["quantity"], "platform": l["platform"],
                    "url": l.get("url"), "currency": l.get("currency"), "asking_price": ask, "market": market,
                    "change_pct": pct, "change_amount": amount,
                    "suggested": suggested(market) if same_cur else None, "last_sold": comp,
                    "needs_platform_update": bool(l.get("needs_platform_update")), "warnings": warnings})
    return out


async def table(db) -> dict:
    items = await _listed(db)
    rates = await get_rates(db)
    rows = []
    for r in await svc.valuate_items(db, items):
        comps = await _last_comps(db, r["item"], rates)
        rows += _rows_for(r, comps[0] if comps else None)
    rows.sort(key=lambda x: (x["change_pct"] is None, -abs(x["change_pct"] or 0)))
    return {"markup_pct": settings.reprice_markup_pct, "threshold_pct": settings.reprice_threshold_pct, "rows": rows}


async def confirm(db, body: RepriceConfirmIn) -> dict:
    """Saves the new asking price on that listing (other listings and `listed_at` kept) and flags it for the platform."""
    it = await db.collection_items.find_one({"_id": svc.oid(body.item_id)})
    if not it or sale.status_of(it) != "listed":
        raise HTTPException(404, "listed stack not found")
    listings, hit = [], False
    for l in sale.sale_of(it)["listings"]:
        l = {k: v for k, v in l.items() if k != "asking_base"}
        if l["platform"] == body.platform:
            l.update(asking_price=body.asking_price, needs_platform_update=True)
            hit = True
        listings.append(l)
    if not hit:
        raise HTTPException(404, f"no {body.platform} listing on this stack")
    return await sale.set_sale(db, body.item_id, StackSaleIn(status="listed", listings=listings))


async def _event(db, key: str, text: str, item: dict, etype: str, now: datetime, **extra) -> bool:
    try:
        await db.alert_events.insert_one({"type": etype, "key": key, "rule": text, "name": extra.pop("name", None),
                                          "card_id": item["card_id"], "item_id": str(item["_id"]),
                                          "fired_at": now, "read": False, **extra})
    except DuplicateKeyError:
        return False
    return True


def _eur(c: int | None, cur: str | None = None) -> str:
    return "n/a" if c is None else f"{c / 100:.2f} {cur or settings.base_currency}"


async def evaluate(db) -> dict:
    """Inbox events for listed stacks: market moved >= threshold from the asking price (once per stack, platform and
    day) and new sold comps of the same card and grade since listing (once per comp). Idempotent, never raises."""
    now = datetime.now(timezone.utc)
    day = now.strftime("%Y-%m-%d")
    moved = comps_new = 0
    try:
        items = await _listed(db)
        rates = await get_rates(db)
        for r in await svc.valuate_items(db, items):
            item, name = r["item"], (r["card"] or {}).get("name")
            for row in _rows_for(r, None):
                if row["change_pct"] is not None and abs(row["change_pct"]) >= settings.reprice_threshold_pct:
                    word = "above" if row["change_amount"] > 0 else "below"
                    txt = (f"{name}: market {_eur(row['market'])} is {abs(row['change_pct']):g}% {word} your asking "
                           f"{_eur(row['asking_price'])} on {row['platform']}")
                    moved += await _event(db, f"reprice:{item['_id']}:{row['platform']}:{day}", txt, item, "reprice", now,
                                          name=name, value=row["market"], prev=row["asking_price"], pct=row["change_pct"])
            listed = [l.get("listed_at") for l in (item.get("sale") or {}).get("listings") or [] if l.get("listed_at")]
            since = (datetime.fromisoformat(min(listed)).replace(tzinfo=timezone.utc) if listed
                     else now - timedelta(days=DEFAULT_COMP_DAYS))
            asks = [l["asking_price"] for l in (item.get("sale") or {}).get("listings") or []]
            for c in await _last_comps(db, item, rates, since, COMPS_PER_STACK):
                txt = (f"{name}: same card sold for {_eur(c['price'], c['currency'])} ({c['source']}, {c['sold_at']}"
                       f"{', condition unknown' if c['condition_unknown'] else ''}); your ask {_eur(min(asks))}")
                comps_new += await _event(db, f"sold:{item['_id']}:{c['id']}", txt, item, "sold_comp", now, name=name,
                                          value=c["price_base"], prev=min(asks))
    except Exception:  # noqa: BLE001 - never breaks a snapshot / fetch run
        log.exception("reprice evaluation failed")
    return {"price_moves": moved, "sold_comps": comps_new}
