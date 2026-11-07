"""Multi-signal print matching (name + collector number + printed total + set code) and the field parsers."""
import pytest

from app.providers.catalog.pokemontcg import map_card
from app.providers.ocr import CardFields, OcrLine
from app.providers.ocr.fields import parse_hp, parse_number, parse_set_code
from app.services import scan
from tests.conftest import CARD


def pc(set_id, num, total, code, rel, name="Charizard"):
    return map_card({**CARD, "id": f"{set_id}-{num}", "name": name, "number": num, "tcgplayer": {}, "cardmarket": {},
                     "set": {"id": set_id, "name": set_id, "printedTotal": total, "ptcgoCode": code,
                             "releaseDate": rel}})


class FieldOcr:
    def __init__(self, line, fields):
        self.line, self.fields = line, fields

    async def read_lines(self, image):
        return [OcrLine(self.line, 90.0, 0.05)]

    async def read_fields(self, image):
        return self.fields


@pytest.fixture
async def cat(db):
    scan.reset_names_cache()
    await db.cards.insert_many([
        pc("base1", "4", 102, "BS", "1999/01/09"), pc("base2", "4", 64, "JU", "1999/06/16"),
        pc("xy12", "11", 108, "EVO", "2016/11/02"), pc("sv3pt5", "6", 165, "MEW", "2023/09/22", "Charizard ex"),
        pc("sv3pt5", "7", 165, "MEW", "2023/09/22", "Squirtle")])
    return db


def ids(res):
    return [c["set"]["id"] for c in res["cards"]]


async def test_number_and_total_put_the_right_print_first_and_keep_the_rest(cat):
    res = await scan.identify(cat, FieldOcr("Charizard", CardFields(number="4", printed_total=102, flat=True)), b"x")
    assert ids(res)[0] == "base1"
    assert res["cards"][0]["signals"] == ["name", "number", "total"]
    assert res["cards"][0]["match_label"] == "name + number + printed total match"
    assert {"base2", "xy12"} <= set(ids(res))  # nothing is dropped: the user can still pick another print
    assert res["exact"] is True and res["read"]["number"] == "4"


async def test_number_alone_leaves_ties_so_not_exact(cat):
    res = await scan.identify(cat, FieldOcr("Charizard", CardFields(number="4")), b"x")
    assert set(ids(res)[:2]) == {"base1", "base2"}  # both have #4, newest set first inside the tie
    assert ids(res)[0] == "base2"
    assert res["exact"] is False


async def test_set_code_narrows_when_readable_and_known(cat):
    res = await scan.identify(cat, FieldOcr("Charizard", CardFields(number="4", set_code="BS")), b"x")
    assert ids(res)[0] == "base1" and "set" in res["cards"][0]["signals"] and res["exact"] is True


async def test_unknown_set_code_is_ignored(cat):
    res = await scan.identify(cat, FieldOcr("Charizard", CardFields(number="4", printed_total=102, set_code="ZZZ")), b"x")
    assert "set" not in res["cards"][0]["signals"]


async def test_nothing_read_keeps_name_order(cat):
    res = await scan.identify(cat, FieldOcr("Charizard", CardFields()), b"x")
    assert ids(res) == ["xy12", "base2", "base1", "sv3pt5"]  # best name first, newest set first, ex form last
    assert all(c["signals"] == ["name"] for c in res["cards"]) and res["exact"] is False


async def test_ocr_without_read_fields_still_works(cat):
    class NameOnly:
        async def read_lines(self, image):
            return [OcrLine("Charizard", 90.0, 0.05)]
    res = await scan.identify(cat, NameOnly(), b"x")
    assert res["read"] is None and res["cards"]


async def test_number_and_total_find_candidates_when_name_is_unreadable(cat):
    res = await scan.identify(cat, FieldOcr("zzzqx", CardFields(number="11", printed_total=108)), b"x")
    assert ids(res) == ["xy12"] and res["cards"][0]["signals"] == ["number", "total"]
    assert res["confidence"] == "low"


async def test_number_without_total_does_not_search_the_whole_catalog(cat):
    res = await scan.identify(cat, FieldOcr("zzzqx", CardFields(number="4")), b"x")
    assert res["cards"] == []


async def test_failed_field_read_does_not_break_the_name_result(cat):
    from app.providers.ocr import OcrUnavailable

    class Broken(FieldOcr):
        async def read_fields(self, image):
            raise OcrUnavailable("boom")
    res = await scan.identify(cat, Broken("Charizard", None), b"x")
    assert res["cards"] and res["read"] is None


@pytest.mark.parametrize("text,want", [
    ("127/182", ("127", 182)), ("127 / 182", ("127", 182)), ("041/167", ("41", 167)), ("4/102", ("4", 102)),
    ("1271182", ("127", 182)), ("x 31/128 .", ("31", 128)), ("12", None), ("", None), ("a/b", None)])
def test_parse_number(text, want):
    assert parse_number(text) == want


@pytest.mark.parametrize("text,want", [("PAR EN", "PAR"), ("PAREN", "PAR"), ("EN", None), ("a", None), ("TWM EN", "TWM")])
def test_parse_set_code(text, want):
    assert parse_set_code(text) == want


@pytest.mark.parametrize("text,want", [("70", 70), ("HP 190", 190), ("7", None), ("77", None), ("", None)])
def test_parse_hp(text, want):
    assert parse_hp(text) == want
