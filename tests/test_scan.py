from datetime import datetime, timezone

from bson import ObjectId

import httpx
import pytest

from app.config import settings
from app.main import app
from app.providers.catalog.pokemontcg import map_card
from app.providers.ocr import ImageError, OcrLine
from app.services import scan
from tests.conftest import CARD

SETS = {"base1": ("Base", "1999/01/09"), "base2": ("Jungle", "1999/06/16"), "sv3pt5": ("151", "2023/09/22")}


def card(set_id: str, num: str, name: str = "Charizard", variants=("holofoil",), **kw) -> dict:
    nm, rel = SETS.get(set_id, (set_id, "2020/01/01"))
    tp = {"prices": {v: {"market": 10} for v in variants}} if variants else {}
    return map_card({**CARD, "id": f"{set_id}-{num}", "name": name, "number": num, "tcgplayer": tp, "cardmarket": {},
                     "set": {"id": set_id, "name": nm, "printedTotal": 102, "releaseDate": rel}, **kw})


class FakeOcr:
    def __init__(self, *lines, conf=90.0, error=None):
        self.lines, self.error = [OcrLine(t, conf, 0.05) for t in lines], error

    async def read_lines(self, image: bytes):
        if self.error:
            raise self.error
        return self.lines


@pytest.fixture
async def cat(db):
    scan.reset_names_cache()
    await db.cards.insert_many([
        card("base1", "4"), card("base2", "99", "Charizard"), card("sv3pt5", "6", "Charizard ex"),
        card("sv3pt5", "25", "Pikachu"), card("sv3pt5", "26", "Pikachu V"), card("sv3pt5", "7", "Squirtle")])
    return db


def names(res):
    return [c["name"] for c in res["cards"]]


async def test_exact_name_lists_every_print_newest_first(cat):
    res = await scan.identify(cat, FakeOcr("BASIC Charizard HP 120"), b"x")
    assert res["confidence"] == "high"
    assert names(res) == ["Charizard", "Charizard", "Charizard ex"]  # ex/V forms follow (the glyph is rarely read)
    sets = [c["set"]["id"] for c in res["cards"] if c["name"] == "Charizard"]
    assert sets == ["base2", "base1"]  # newest first


async def test_ocr_typo_still_finds_candidates(cat):
    res = await scan.identify(cat, FakeOcr("Charizad"), b"x")
    assert "Charizard" in names(res)
    assert res["confidence"] in ("medium", "low")  # a guess is never "high"


async def test_suffix_names_are_kept_apart(cat):
    res = await scan.identify(cat, FakeOcr("Pikachu V HP 190"), b"x")
    assert names(res)[0] == "Pikachu V"


async def test_unreadable_text_gives_no_cards(cat):
    res = await scan.identify(cat, FakeOcr("zzzqx"), b"x")
    assert res["cards"] == [] and res["confidence"] == "none"


async def test_card_shape_has_picker_fields_and_edition_note(cat):
    res = await scan.identify(cat, FakeOcr("Charizard"), b"x")
    base = next(c for c in res["cards"] if c["set"]["id"] == "base1")
    assert base["number"] == "4" and base["printed_total"] == 102 and base["year"] == 1999
    assert base["edition_note"] and "Shadowless" in base["edition_note"]
    assert base["variants"] == ["holofoil"]
    modern = next(c for c in (await scan.identify(cat, FakeOcr("Squirtle"), b"x"))["cards"])
    assert modern["edition_note"] is None


async def test_owned_stack_is_reported(cat):
    from app.db.models import CollectionIn
    await scan.add_scanned(cat, CollectionIn(card_id="pokemon:base1-4", variant="holofoil", condition="NM"))
    res = await scan.identify(cat, FakeOcr("Charizard"), b"x")
    base = next(c for c in res["cards"] if c["set"]["id"] == "base1")
    assert base["owned_qty"] == 1 and base["owned"][0]["condition"] == "NM"
    assert res["cards"][0]["id"] == "pokemon:base1-4"  # owned first within the best name


async def test_add_merges_into_existing_stack_and_logs_event(cat):
    from app.db.models import CollectionIn
    body = CollectionIn(card_id="pokemon:base1-4", variant="holofoil", condition="NM")
    one = await scan.add_scanned(cat, body)
    two = await scan.add_scanned(cat, body)
    assert one["stack"]["quantity"] == 1 and two["stack"]["quantity"] == 2
    assert two["stack"]["id"] == one["stack"]["id"]
    assert await cat.collection_items.count_documents({}) == 1
    assert two["label"] == "Charizard, Base" and two["event"]["quantity_after"] == 2
    first = await scan.events_after(cat, None)  # fresh page: cursor only
    assert first["events"] == [] and first["latest"] == two["event"]["id"]
    await scan.add_scanned(cat, body)
    later = await scan.events_after(cat, first["latest"])
    assert [e["quantity_after"] for e in later["events"]] == [3]


async def test_search_by_typed_name(cat):
    res = await scan.search(cat, "pikachu")
    assert sorted(c["name"] for c in res["cards"]) == ["Pikachu", "Pikachu V"]


# --- API + phone mode ---------------------------------------------------------------------------------

@pytest.fixture
def phone(monkeypatch):
    monkeypatch.setattr(settings, "lan_gate_secret", "s3cret")
    monkeypatch.setattr(settings, "lan_origin", "https://localhost")
    return {"x-moc-gate": "s3cret"}


def client(host="localhost"):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=f"http://{host}")


async def test_identify_api_never_adds(cat, monkeypatch):
    monkeypatch.setattr("app.api.scan.get_ocr", lambda: FakeOcr("Charizard"))
    async with client() as c:
        r = await c.post("/api/scan/identify", content=b"img")
        assert r.status_code == 200 and r.json()["cards"]
    assert await cat.collection_items.count_documents({}) == 0


async def test_identify_rejects_bad_images_and_size(cat, monkeypatch):
    monkeypatch.setattr("app.api.scan.get_ocr", lambda: FakeOcr(error=ImageError("not a readable image")))
    async with client() as c:
        assert (await c.post("/api/scan/identify", content=b"zz")).status_code == 400
        assert (await c.post("/api/scan/identify", content=b"")).status_code == 400
        monkeypatch.setattr(settings, "scan_max_image_mb", 0)
        assert (await c.post("/api/scan/identify", content=b"zz")).status_code == 413


async def test_add_validates_raw_needs_condition(cat):
    async with client() as c:
        assert (await c.post("/api/scan/add", json={"card_id": "pokemon:base1-4"})).status_code == 422
        r = await c.post("/api/scan/add", json={"card_id": "pokemon:base1-4", "variant": "holofoil",
                                                "condition": "NM", "quantity": 1,
                                                "acquired": {"type": "pulled", "price": 0, "currency": "EUR"}})
        assert r.status_code == 201 and r.json()["stack"]["acquired"]["type"] == "pulled"
        assert (await c.post("/api/scan/add", json={"card_id": "pokemon:nope-1", "condition": "NM"})).status_code == 404


async def test_phone_mode_only_reaches_the_scan_allowlist(cat, phone, monkeypatch):
    monkeypatch.setattr("app.api.scan.get_ocr", lambda: FakeOcr("Charizard"))
    async with client() as c:
        assert (await c.get("/api/scan/me", headers=phone)).status_code == 200
        assert (await c.post("/api/scan/identify", content=b"i", headers=phone)).status_code == 200
        assert (await c.get("/api/scan/search?q=pikachu", headers=phone)).status_code == 200
        assert (await c.get("/api/scan/session", headers=phone)).json() == {"session": None}
        add = {"card_id": "pokemon:base1-4", "variant": "holofoil", "condition": "NM"}
        assert (await c.post("/api/scan/add", json=add, headers={**phone, "origin": "https://localhost"})).status_code == 201
        for method, path in [("GET", "/api/collection"), ("GET", "/api/collection/export"), ("POST", "/api/collection"),
                             ("POST", "/api/collection/import"), ("GET", "/api/cards"), ("GET", "/api/admin/jobs"),
                             ("POST", "/api/admin/snapshot"), ("GET", "/api/wishlist"), ("GET", "/api/alerts"),
                             ("GET", "/docs"), ("GET", "/api/scan/events"), ("GET", "/api/scan/status"),
                             ("POST", "/api/scan/sessions"), ("DELETE", "/api/scan/sessions/abc"),
                             ("POST", "/api/collection/abc/remove"), ("GET", "/api/collection/exits")]:
            r = await c.request(method, path, headers=phone)
            assert r.status_code == 403, (method, path, r.status_code)


async def test_phone_mode_wrong_secret_origin_and_host(cat, phone):
    async with client() as c:
        assert (await c.get("/api/scan/me", headers={"x-moc-gate": "nope"})).status_code == 403
        add = {"card_id": "pokemon:base1-4", "variant": "holofoil", "condition": "NM"}
        r = await c.post("/api/scan/add", json=add, headers={**phone, "origin": "http://localhost:5180"})
        assert r.status_code == 403  # the laptop origin does not work from the phone
    async with client("127.0.0.1") as c:
        assert (await c.get("/api/scan/me", headers=phone)).status_code == 403  # host is not the tailnet host


async def test_gate_header_refused_when_phone_mode_is_off(monkeypatch):
    monkeypatch.setattr(settings, "lan_gate_secret", "")
    async with client() as c:
        assert (await c.get("/api/scan/me", headers={"x-moc-gate": ""})).status_code == 403


async def test_laptop_endpoints_work_without_gate(cat, monkeypatch):
    monkeypatch.setattr(settings, "lan_origin", "https://moc.tail.ts.net")
    monkeypatch.setattr(settings, "lan_gate_secret", "s")
    monkeypatch.setattr(settings, "lan_login", "")
    async with client() as c:
        st = (await c.get("/api/scan/status")).json()
        assert st == {"enabled": True, "url": "https://moc.tail.ts.net/scan", "login": None}
        assert (await c.get("/api/scan/events")).json() == {"events": [], "latest": None}


async def test_evolves_from_line_does_not_pick_the_previous_stage(cat):
    await cat.cards.insert_one(card("sv3pt5", "30", "Charmeleon"))
    scan.reset_names_cache()
    res = await scan.identify(cat, FakeOcr("Evolves from Charmeleon"), b"x")
    assert res["confidence"] == "none" and res["cards"] == []


async def test_base_name_also_brings_ex_and_v_forms(cat):
    res = await scan.identify(cat, FakeOcr("Charizard"), b"x")
    assert "Charizard ex" in names(res)  # the printed "ex" glyph is rarely read
    assert names(res)[0] == "Charizard"  # base name still ranks first


class StagedOcr:
    def __init__(self, *batches):
        self.batches, self.used = batches, 0

    async def stages(self, image: bytes):
        for b in self.batches:
            self.used += 1
            yield [OcrLine(t, 90.0, 0.05) for t in b]


async def test_staged_read_stops_at_first_confident_exact_name(cat):
    ocr = StagedOcr(["xx qq"], ["Squirtle"], ["Pikachu"])
    res = await scan.identify(cat, ocr, b"x")
    assert ocr.used == 2 and res["names"][0] == "squirtle"


async def test_staged_read_keeps_going_when_nothing_matches(cat):
    ocr = StagedOcr(["xx qq"], ["zzz"], ["Charizad"])
    res = await scan.identify(cat, ocr, b"x")
    assert ocr.used == 3 and res["names"] and res["names"][0].startswith("charizard")


async def test_session_lifecycle_and_events_filter(cat):
    from app.db.models import CollectionIn
    assert await scan.current_session(cat) is None
    one = await scan.start_session(cat)
    assert (await scan.current_session(cat))["id"] == one["id"]
    two = await scan.start_session(cat)  # a new session closes the old one
    assert (await scan.current_session(cat))["id"] == two["id"]
    assert await scan.close_session(cat, two["id"]) and await scan.current_session(cat) is None
    assert not await scan.close_session(cat, "nope")
    sess = await scan.start_session(cat)
    cur = (await scan.events_after(cat, None))["latest"] or "000000000000000000000000"
    body = CollectionIn(card_id="pokemon:base1-4", variant="holofoil", condition="NM")
    await scan.add_scanned(cat, body, sess["id"])
    await scan.add_scanned(cat, body)  # standalone phone add: not in the session feed
    mine = await scan.events_after(cat, cur, sess["id"])
    assert [e["session_id"] for e in mine["events"]] == [sess["id"]] and mine["events"][0]["condition"] == "NM"


async def test_idle_session_expires(cat):
    from datetime import timedelta
    await scan.start_session(cat)
    await cat.scan_sessions.update_many({}, {"$set": {"last_activity": datetime.now(timezone.utc) - timedelta(minutes=31)}})
    assert await scan.current_session(cat) is None


async def test_undo_last_add_new_stack_deletes_it(cat):
    from app.db.models import CollectionIn
    a = await scan.add_scanned(cat, CollectionIn(card_id="pokemon:base1-4", variant="holofoil", condition="NM"))
    r = await scan.undo(cat, a["event"]["id"])
    assert r["deleted"] and await cat.collection_items.count_documents({}) == 0
    assert await cat.collection_exits.count_documents({}) == 0  # a mistaken add is not an exit
    with pytest.raises(scan.ScanError):
        await scan.undo(cat, a["event"]["id"])  # twice


async def test_undo_merge_restores_quantity_and_cost(cat):
    from app.db.models import CollectionIn
    acq = lambda p: {"type": "purchased", "price": p, "currency": "EUR"}
    await scan.add_scanned(cat, CollectionIn(card_id="pokemon:base1-4", variant="holofoil", condition="NM", acquired=acq(100)))
    b = await scan.add_scanned(cat, CollectionIn(card_id="pokemon:base1-4", variant="holofoil", condition="NM", acquired=acq(300)))
    assert (await cat.collection_items.find_one({}))["acquired"]["price"] == 200
    r = await scan.undo(cat, b["event"]["id"])
    st = await cat.collection_items.find_one({})
    assert r["quantity"] == 1 and st["quantity"] == 1 and st["acquired"]["price"] == 100
    kinds = [e["kind"] async for e in cat.scan_events.find().sort("_id", 1)]
    assert kinds == ["add", "add", "undo"]


async def test_undo_only_latest_and_within_window(cat):
    from datetime import timedelta
    from app.db.models import CollectionIn
    a = await scan.add_scanned(cat, CollectionIn(card_id="pokemon:base1-4", variant="holofoil", condition="NM"))
    b = await scan.add_scanned(cat, CollectionIn(card_id="pokemon:sv3pt5-7", condition="NM"))
    with pytest.raises(scan.ScanError, match="last card"):
        await scan.undo(cat, a["event"]["id"])
    await cat.scan_events.update_one({"_id": ObjectId(b["event"]["id"])},
                                     {"$set": {"at": datetime.now(timezone.utc) - timedelta(minutes=11)}})
    with pytest.raises(scan.ScanError, match="too late"):
        await scan.undo(cat, b["event"]["id"])


async def test_lookup_number_total_and_set(cat):
    r = await scan.lookup(cat, "4/102")
    assert [c["id"] for c in r["cards"]] == ["pokemon:base1-4"] and r["exact"] is True
    assert r["cards"][0]["signals"] == ["number", "total"]
    assert (await scan.lookup(cat, "99", "jungle"))["cards"][0]["id"] == "pokemon:base2-99"  # set name fragment
    assert (await scan.lookup(cat, "99", "base2"))["cards"][0]["signals"] == ["number", "set"]  # set id
    assert (await scan.lookup(cat, "004"))["cards"][0]["id"] == "pokemon:base1-4"  # padded
    assert (await scan.lookup(cat, "4/999"))["cards"] == []  # wrong printed total
    assert (await scan.lookup(cat, "4", "nosuchset"))["cards"] == []


async def test_lookup_api_phone_allowed(cat, phone):
    async with client() as c:
        r = await c.get("/api/scan/lookup?number=4/102", headers=phone)
        assert r.status_code == 200 and r.json()["cards"][0]["id"] == "pokemon:base1-4"
