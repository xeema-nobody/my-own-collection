"""Demo database for UI checks: `owncollection_demo`, separate from the real `owncollection`.

  docker compose run --rm app python -m app.scripts.demo_db create|status|drop

`create` copies the Mew ex 151 #205 card (+ prices, sales, matches, FX) and one unpriced card from the real
DB and seeds collection items that exercise every valuation match (exact, bucket, lower, raw_fallback,
none, thin sold; `lower` only occurs when a company has a lower grade but no 10: covered by unit tests) plus a snapshot. Only the demo DB is ever written or dropped.
Run the app against it with docker-compose.demo.yml (see docs/README.md).
"""
import asyncio
import sys
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings
from app.db.models import CollectionIn
from app.services import collection
from app.services.snapshots import take_snapshot

REAL_DB, DEMO_DB = "owncollection", "owncollection_demo"
MEW = "pokemon:sv3pt5-205"
BY_CARD = ("prices", "sales", "product_matches")  # collections keyed by card_id


def seed_items(unpriced_id: str) -> list[CollectionIn]:
    graded = lambda company, grade, **kw: CollectionIn(  # noqa: E731
        card_id=MEW, variant="holofoil", grading={"company": company, "grade": grade}, **kw)
    cost = {"price": 5000, "currency": "EUR"}
    return [
        CollectionIn(card_id=MEW, variant="holofoil", condition="NM", acquired=cost),                 # raw
        graded("PSA", 9, acquired=cost),                                                              # exact, sold
        graded("PSA", 8, quantity=2),                                                                 # exact, qty 2
        graded("PSA", 7),                                                                             # bucket G7
        graded("BGS", 9.5),                                                                           # thin sold
        graded("OTHER", 10),                                                                          # raw_fallback
        CollectionIn(card_id=unpriced_id, condition="NM", acquired={"price": 300, "currency": "EUR"}),  # none
    ]


async def create(client) -> None:
    real, demo = client[REAL_DB], client[DEMO_DB]
    if await demo.collection_items.count_documents({}):
        sys.exit("demo DB already seeded: run `drop` first")
    unpriced = await real.cards.find_one({"tcg": "pokemon", "price_base": None, "latest_price": {"$in": [None, {}]}},
                                         {"_id": 1})
    ids = [MEW] + ([unpriced["_id"]] if unpriced else [])
    cards = await real.cards.find({"_id": {"$in": ids}}).to_list(None)
    for c in cards:
        await demo.cards.replace_one({"_id": c["_id"]}, c, upsert=True)
    set_ids = {c["set"]["id"] for c in cards}
    for s in await real.sets.find({"external_id": {"$in": list(set_ids)}}).to_list(None):
        await demo.sets.replace_one({"_id": s["_id"]}, s, upsert=True)
    for name in BY_CARD:
        for d in await real[name].find({"card_id": {"$in": ids}}).to_list(None):
            await demo[name].replace_one({"_id": d["_id"]}, d, upsert=True)
    for d in await real.fx_rates.find({}).to_list(None):
        await demo.fx_rates.replace_one({"_id": d["_id"]}, d, upsert=True)
    for i in seed_items(unpriced["_id"] if unpriced else MEW):
        await collection.add(demo, i)
    # a week of fake history so the chart and movers have data: older snapshots from today's valuation
    snap = await take_snapshot(demo)
    for n in (7, 3):
        day = (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%d")
        scale = 0.9 if n == 7 else 0.95
        await demo.collection_snapshots.replace_one({"date": day}, {
            **{k: v for k, v in snap.items() if k != "_id"}, "date": day,
            "total_value": round(snap["total_value"] * scale),
            "totals_by_source": {k: round(v * scale) for k, v in snap["totals_by_source"].items()}}, upsert=True)
    print(f"demo DB ready: {len(ids)} cards, {await demo.collection_items.count_documents({})} items")


async def main(cmd: str) -> None:
    if DEMO_DB == REAL_DB or not DEMO_DB.endswith("_demo"):
        sys.exit("refusing: demo name misconfigured")
    client = AsyncIOMotorClient(settings.mongo_url, tz_aware=True)
    if cmd == "create":
        await create(client)
    elif cmd == "drop":
        await client.drop_database(DEMO_DB)
        print(f"dropped {DEMO_DB}")
    elif cmd == "status":
        demo = client[DEMO_DB]
        print({n: await demo[n].count_documents({}) for n in ("cards", "collection_items", "collection_snapshots")})
    else:
        sys.exit("usage: python -m app.scripts.demo_db create|status|drop")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else ""))
