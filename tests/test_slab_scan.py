"""Slabs through the scan API: label read, duplicate cert, Other grader, never valued at the raw price."""
import httpx
import pytest

from app.main import app
from app.providers.grading.base import CertInfo
from app.providers.ocr import OcrLine
from app.providers.ocr.slab import SlabRead
from app.providers.ocr.slabfields import SlabLabel
from app.services import scan
from app.services.collection import make_stack_key
from tests.test_scan import card

LABEL = SlabLabel("PSA", 9.0, "56941091", "MINT", False, True)


class SlabOcr:
    def __init__(self, label=LABEL):
        self.label, self.slab_calls = label, 0

    async def read_lines(self, image):
        return [OcrLine("Charizard", 90.0, 0.05)]

    async def read_slab(self, image):
        self.slab_calls += 1
        return SlabRead(self.label) if self.label else None


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """No live cert lookup in tests: PSA 56941091 'is' a Charizard #4 of Base."""
    async def fake(grader, cert, client=None, transport=None):
        return CertInfo(grader, cert, "found", f"https://x/{cert}", name="Charizard", number="4", grade=9.0)
    monkeypatch.setattr("app.providers.grading.registry.lookup", fake)


@pytest.fixture
async def cat(db):
    scan.reset_names_cache()
    await db.cards.insert_many([card("base1", "4")])
    return db


@pytest.fixture
async def client(db):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as c:
        yield c


async def test_slab_label_is_returned_with_the_cert_page_card(cat):
    res = await scan.identify(cat, SlabOcr(), b"x", slab=True)
    assert res["slab"] == {"grader": "PSA", "grade": 9.0, "cert": "56941091", "tier": "MINT", "grader_seen": False}
    assert [c["name"] for c in res["cards"]] == ["Charizard"]
    assert res["cert"]["cert"]["status"] == "found" and res["cert"]["needs_confirm"] is True  # PSA: user confirms
    assert res["exact"] is False


async def test_slab_mode_never_runs_the_raw_card_read(cat):
    class Boom(SlabOcr):
        async def read_lines(self, image):
            raise AssertionError("identify_card must not run in slab mode")
        async def read_fields(self, image):
            raise AssertionError("identify_card must not run in slab mode")
    assert (await scan.identify(cat, Boom(), b"x", slab=True))["slab"]["cert"] == "56941091"


async def test_slab_mode_without_a_readable_cert_returns_label_only(cat):
    res = await scan.identify(cat, SlabOcr(SlabLabel("PSA", 9.0, None, "MINT", False, True)), b"x", slab=True)
    assert res["cards"] == [] and res["cert"] is None and res["slab"]["grade"] == 9.0


async def test_label_only_read_when_card_is_not_an_exact_hit(cat):
    ocr = SlabOcr()
    res = await scan.identify(cat, ocr, b"x")  # name only, no number: not exact -> label is tried
    assert res["exact"] is False and ocr.slab_calls == 1 and res["slab"]["grade"] == 9.0
    assert (await scan.identify(cat, SlabOcr(None), b"x"))["slab"] is None  # raw card: no slab key content


async def test_raw_mode_flags_a_slab_it_found_but_slab_mode_does_not(cat):
    raw = await scan.identify(cat, SlabOcr(), b"x")
    assert raw["detected"] is True and raw["slab"]["grade"] == 9.0
    assert (await scan.identify(cat, SlabOcr(), b"x", slab=True))["detected"] is False  # already in slab mode
    assert (await scan.identify(cat, SlabOcr(None), b"x"))["detected"] is False  # bare raw card


async def test_slab_mode_always_reads_the_label_even_on_an_exact_hit(cat):
    class Exact(SlabOcr):
        async def read_fields(self, image):
            from app.providers.ocr import CardFields
            return CardFields(number="4", printed_total=102)
    ocr = Exact()
    res = await scan.identify(cat, ocr, b"x", slab=True)
    assert ocr.slab_calls == 1 and res["slab"] is not None


async def test_reader_without_slab_support_still_identifies(cat):
    class Plain:
        async def read_lines(self, image):
            return [OcrLine("Charizard", 90.0, 0.05)]
    res = await scan.identify(cat, Plain(), b"x", slab=True)
    assert res["slab"] is None and res["cards"] == []


def body(**g):
    return {"card_id": "pokemon:base1-4", "grading": {"company": "PSA", "grade": 9, "cert_number": "56941091", **g}}


async def test_same_cert_twice_is_one_stack_and_not_added_again(cat, client):
    a = await client.post("/api/scan/add", json=body())
    b = await client.post("/api/scan/add", json=body())
    assert a.status_code == b.status_code == 201
    assert b.json()["stack"]["quantity"] == 1 and b.json()["stack"]["duplicate"] is True
    assert b.json()["event"]["quantity_added"] == 0
    assert await cat.collection_items.count_documents({}) == 1
    undo = await client.post("/api/scan/undo", json={"event_id": b.json()["event"]["id"]})
    assert undo.status_code == 409  # nothing was added, nothing to take back


async def test_other_slab_needs_a_grader_name_and_keeps_it(cat, client):
    no_name = await client.post("/api/scan/add", json=body(company="OTHER", cert_number=None))
    assert no_name.status_code == 422
    ok = await client.post("/api/scan/add", json=body(company="OTHER", cert_number=None, grader_name="  TAG  "))
    assert ok.status_code == 201 and ok.json()["stack"]["grading"]["grader_name"] == "TAG"


def test_other_graders_do_not_share_a_stack():
    g = lambda n: {"company": "OTHER", "grade": 9, "cert_number": None, "grader_name": n}  # noqa: E731
    k = lambda gr: make_stack_key("c", None, "en", None, gr)  # noqa: E731
    assert k(g("TAG")) != k(g("Cardgrader")) and k(g("tag")) == k(g("TAG"))
    assert k({"company": "PSA", "grade": 9, "cert_number": None}) == "c||en||PSA|9|"  # existing keys are unchanged


async def test_scanned_slab_without_graded_price_is_not_valued_at_raw(cat, client):
    await client.post("/api/scan/add", json=body(company="OTHER", cert_number=None, grader_name="TAG"))
    r = (await client.get("/api/collection")).json()
    item = r["items"][0]
    assert item["value"] is None and item["needs_price"] is True
