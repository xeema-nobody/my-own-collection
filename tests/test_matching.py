from pathlib import Path

import httpx
import pytest

from app.main import app
from app.providers.price import cardmarket as cm
from app.providers.price.base import AdapterResult
from app.providers.price.match import pick
from app.services import matching
from tests.conftest import make_card
from tests.test_adapters import CARD, PC_PAGES, FakeFetcher
from app.providers.price import get_provider

FX = Path(__file__).parent / "fixtures"
CM_URL = "https://www.cardmarket.com/en/Pokemon/Products/Singles/151/Mew-ex-V3-MEW205"
PC_URL = "https://www.pricecharting.com/game/pokemon-scarlet-&-violet-151/mew-ex-205"


@pytest.fixture
async def client(db):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as c:
        yield c


@pytest.fixture
async def card(db):
    c = make_card("sv3pt5", "205")
    await db.cards.insert_one(c)
    return c["_id"]


@pytest.mark.parametrize("source,url", [
    ("cardmarket_web", "https://www.cardmarket.com.evil.io/en/Pokemon/Products/Singles/x"),
    ("cardmarket_web", "http://www.cardmarket.com/en/Pokemon/Products/Singles/x"),
    ("cardmarket_web", "https://www.cardmarket.com/en/Pokemon/Products/Search?searchString=x"),
    ("cardmarket_web", "https://www.pricecharting.com/game/a/b"),
    ("pricecharting", "https://evil.io/game/a/b"),
    ("altxyz", "https://alt.xyz/browse?q=x"),
])
def test_validate_url_rejects(source, url):
    with pytest.raises(matching.InvalidMatch):
        matching.validate_url(source, url)


def test_validate_url_accepts():
    assert matching.validate_url("cardmarket_web", CM_URL) == CM_URL
    assert matching.validate_url("pricecharting", PC_URL) == PC_URL


def _candidates():
    cands = cm.parse_search((FX / "cardmarket/search_mew_ex_205.html").read_text())
    return pick(CARD, cands)[1]


async def test_needs_match_stores_candidates_idempotently(db, card):
    res = AdapterResult("needs_match", candidates=_candidates())
    await matching.record_result(db, card, "cardmarket_web", res)
    await matching.record_result(db, card, "cardmarket_web", res)
    m = (await matching.get_matches(db, card))["cardmarket_web"]
    assert m["url"] is None and len(m["candidates"]) == 3 and m["candidates"][0]["url"]
    assert await db.product_matches.count_documents({}) == 1


async def test_auto_then_user_precedence(db, card):
    await matching.record_result(db, card, "pricecharting", AdapterResult("ok", url=PC_URL))
    assert await matching.known_url(db, card, "pricecharting") == PC_URL
    other = PC_URL + "-2"
    await matching.confirm(db, card, "pricecharting", other)
    await matching.record_result(db, card, "pricecharting", AdapterResult("ok", url=PC_URL))   # no overwrite, no error
    await matching.record_result(db, card, "pricecharting", AdapterResult("needs_match", candidates=_candidates()))
    m = (await matching.get_matches(db, card))["pricecharting"]
    assert m["url"] == other and m["confirmed_by"] == "user"


async def test_other_statuses_and_unmatchable_sources_noop(db, card):
    for st in ("not_found", "blocked", "error", "login_timeout"):
        await matching.record_result(db, card, "pricecharting", AdapterResult(st, url=PC_URL))
    await matching.record_result(db, card, "altxyz", AdapterResult("ok", url="https://alt.xyz/x"))
    assert await db.product_matches.count_documents({}) == 0


async def test_api_flow(client, db, card):
    r = await client.get(f"/api/cards/{card}/match")
    assert r.status_code == 200 and set(r.json()) == {"pricecharting", "cardmarket_web"}
    assert r.json()["cardmarket_web"]["url"] is None
    await matching.record_result(db, card, "cardmarket_web", AdapterResult("needs_match", candidates=_candidates()))
    r = await client.post(f"/api/cards/{card}/match/cardmarket_web", json={"url": CM_URL})
    assert r.status_code == 200 and r.json()["confirmed_by"] == "user" and r.json()["candidates"] == []
    assert (await client.get(f"/api/cards/{card}/match")).json()["cardmarket_web"]["url"] == CM_URL
    assert (await client.delete(f"/api/cards/{card}/match/cardmarket_web")).status_code == 204
    assert (await client.get(f"/api/cards/{card}/match")).json()["cardmarket_web"]["url"] is None


async def test_api_errors(client, card):
    bad = await client.post(f"/api/cards/{card}/match/cardmarket_web", json={"url": "https://evil.io/x"})
    assert bad.status_code == 422
    assert (await client.post(f"/api/cards/{card}/match/altxyz", json={"url": CM_URL})).status_code == 422
    assert (await client.delete(f"/api/cards/{card}/match/altxyz")).status_code == 422
    assert (await client.post("/api/cards/nope/match/cardmarket_web", json={"url": CM_URL})).status_code == 404
    assert (await client.get("/api/cards/nope/match")).status_code == 404


async def test_stored_match_skips_search(db, card):
    await matching.confirm(db, card, "pricecharting", PC_URL)
    f = FakeFetcher(PC_PAGES)
    url = await matching.known_url(db, card, "pricecharting")
    await get_provider("pricecharting").fetch(CARD, f, known_url=url)
    assert len(f.calls) == 1 and f.calls[0][1] == PC_URL
