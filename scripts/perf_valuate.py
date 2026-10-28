"""Time collection valuation at N synthetic stacks. Read-only on the live db: works in a scratch db
`<db>_perf` (cards sampled from the live catalog) and drops it afterwards.

Usage: docker compose exec app python scripts/perf_valuate.py [N ...]   (default 15 500 2000)
Bar (docs/architecture.md): valuate() < 1 s at 2000 stacks.
"""
import asyncio
import random
import sys
import time
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings
from app.services import collection as coll

CONDS = ["NM", "LP", "MP"]
GRADES = [("PSA", 10), ("PSA", 9), ("BGS", 9.5), ("CGC", 10)]


async def main(sizes: list[int]):
    client = AsyncIOMotorClient(settings.mongo_url, tz_aware=True)
    live, name = client[settings.mongo_db], f"{settings.mongo_db}_perf"
    scratch = client[name]
    await client.drop_database(name)
    try:
        cards = [c async for c in live.cards.find({"price_base": {"$ne": None}}).limit(5000)]
        await scratch.cards.insert_many(cards)
        await scratch.fx_rates.insert_many([r async for r in live.fx_rates.find()])
        now, rng = datetime.now(timezone.utc), random.Random(1)
        print(f"{len(cards)} priced cards sampled; sizes {sizes}")
        for n in sizes:
            await scratch.collection_items.delete_many({})
            items = []
            for i in range(n):
                c, g = rng.choice(cards), rng.random() < 0.3
                grading = dict(zip(("company", "grade"), rng.choice(GRADES))) if g else None
                items.append({"card_id": c["_id"], "variant": None, "language": "en",
                              "condition": None if g else rng.choice(CONDS), "grading": grading,
                              "quantity": rng.randint(1, 3), "acquired": {"price": 500, "currency": "EUR"},
                              "stack_key": f"{c['_id']}|{i}", "created_at": now, "tags": []})
            await scratch.collection_items.insert_many(items)
            t = time.perf_counter()
            rows = await coll.valuate(scratch)
            dt = time.perf_counter() - t
            t = time.perf_counter()
            [coll.present(r) for r in rows]
            print(f"N={n:5d}  valuate {dt * 1000:7.0f} ms   present {(time.perf_counter() - t) * 1000:5.0f} ms"
                  f"   priced {sum(r['value'] is not None for r in rows)}/{n}")
    finally:
        await client.drop_database(name)
        client.close()


if __name__ == "__main__":
    asyncio.run(main([int(a) for a in sys.argv[1:]] or [15, 500, 2000]))
