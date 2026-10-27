import pytest
from pydantic import ValidationError

from app.db.models import CollectionIn
from app.providers.catalog.pokemontcg import extract_prices, map_card
from app.services.search import build_query

CARD = {"id": "base1-4", "name": "Charizard", "number": "4", "supertype": "Pokémon",
        "types": ["Fire"], "rarity": "Rare Holo", "set": {"id": "base1", "name": "Base", "printedTotal": 102},
        "tcgplayer": {"updatedAt": "2026/10/27", "prices": {"holofoil": {"low": 100.5, "mid": 200, "high": 400, "market": 250.1}}},
        "cardmarket": {"updatedAt": "2026/10/27", "prices": {"trendPrice": 180.0, "averageSellPrice": 190, "lowPrice": 120}}}


def test_map_card_and_prices():
    c = map_card(CARD)
    assert c["_id"] == "pokemon:base1-4" and c["variants"] == ["holofoil"]
    assert "4/102" in c["search_text"]
    pts = {p["source"]: p for p in extract_prices(c)}
    assert pts["tcgplayer"]["market"] == 25010 and pts["cardmarket"]["market"] == 18000


def test_missing_price_is_none_not_zero():
    c = map_card({**CARD, "tcgplayer": {"updatedAt": "2026/10/27", "prices": {"normal": {"low": 1}}}, "cardmarket": {}})
    assert extract_prices(c)[0]["market"] is None


def test_search_number_and_tokens():
    q = build_query("charizard 4/102")["$and"]
    assert {"set.printed_total": 102} in q
    assert any("search_text" in x for x in q)


def test_validation():
    with pytest.raises(ValidationError):
        CollectionIn(card_id="x")  # raw needs condition
    with pytest.raises(ValidationError):
        CollectionIn(card_id="x", condition="NM", grading={"company": "PSA", "grade": 9})
    CollectionIn(card_id="x", grading={"company": "PSA", "grade": 9})
