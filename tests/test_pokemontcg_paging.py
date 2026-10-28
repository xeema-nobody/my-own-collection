"""Adaptive paging of the pokemontcg.io adapter against a mocked flaky upstream (no network)."""
import httpx
import pytest

from app.providers.catalog import pokemontcg
from app.providers.catalog.pokemontcg import IncompletePage, PokemonTcgCatalog

TOTAL = 230


def raw(i: int) -> dict:
    return {"id": f"x-{i}", "name": f"C{i}", "number": str(i), "supertype": "Pokémon",
            "set": {"id": "x", "name": "X", "printedTotal": TOTAL}}


def upstream(bad):
    """Handler: 500 when a request window (offset, size) matches `bad(offset, size)`."""
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        q = req.url.params
        size, page = int(q["pageSize"]), int(q["page"])
        off = (page - 1) * size
        calls.append((off, size))
        if bad(off, size):
            return httpx.Response(500)
        return httpx.Response(200, json={"data": [raw(i) for i in range(off, min(off + size, TOTAL))],
                                         "totalCount": TOTAL})
    return handler, calls


def provider(handler):
    return PokemonTcgCatalog(httpx.AsyncClient(base_url="http://up", transport=httpx.MockTransport(handler)))


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    monkeypatch.setattr(pokemontcg, "wait_random_exponential", lambda **kw: __import__("tenacity").wait_none())


async def collect(p):
    return [c["external_id"] async for c in p.iter_cards("x")]


async def test_happy_path_uses_full_pages():
    handler, calls = upstream(lambda o, s: False)
    ids = await collect(provider(handler))
    assert len(ids) == TOTAL and calls == [(0, 100), (100, 100), (200, 100)]


async def test_failed_page_recovers_with_smaller_pages():
    handler, calls = upstream(lambda o, s: s == 100 and o == 100)
    ids = await collect(provider(handler))
    assert ids == [f"x-{i}" for i in range(TOTAL)]  # nothing lost, order kept
    assert (100, 50) in calls and (150, 50) in calls


async def test_recovers_down_to_tiny_pages():
    handler, _ = upstream(lambda o, s: s > 5 and o == 100)
    assert len(await collect(provider(handler))) == TOTAL


async def test_dead_window_is_reported_but_rest_is_yielded():
    handler, _ = upstream(lambda o, s: o <= 100 < o + s and s <= 100)  # card 100 never loads at any size
    p, got = provider(handler), []
    with pytest.raises(IncompletePage) as e:
        async for c in p.iter_cards("x"):
            got.append(c["external_id"])
    assert e.value.missing == [(100, 5)]
    assert len(got) == TOTAL - 5 and "x-100" not in got and "x-229" in got


async def test_first_page_failure_raises_plain_error():
    handler, _ = upstream(lambda o, s: o == 0)
    with pytest.raises(httpx.HTTPStatusError):
        await collect(provider(handler))
