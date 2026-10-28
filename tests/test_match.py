from app.providers.price.base import Candidate
from app.providers.price.match import norm_number, pick, score, strip_variant

CARD = {"name": "Mew ex", "number": "205", "language": "en", "set": {"name": "151"}}


def cand(name="Mew ex", number="205", set_name="Pokemon Scarlet & Violet 151", lang="en"):
    return Candidate("u/" + name + number + set_name, name, name, set_name, number, lang)


def test_norm_number():
    assert norm_number("205/165") == "205"
    assert norm_number("005") == "5"
    assert norm_number("SVP 205".split()[-1]) == "205"
    assert norm_number("TG05") == "tg5"


def test_strip_variant():
    assert strip_variant("Mew Ex [Metal]") == ("mew ex", True)
    assert strip_variant("Mew ex") == ("mew ex", False)


def test_number_and_language_must_match():
    assert score(CARD, cand(number="206")) == 0
    assert score(CARD, cand(lang="ja")) == 0
    assert score(CARD, cand()) >= 0.8


def test_variant_penalised_and_best_accepted():
    best, ranked = pick(CARD, [cand("Mew Ex [Metal]"), cand(), cand("Mew ex [Jumbo]")])
    assert best and best.name == "Mew ex" and len(ranked) == 3


def test_tie_is_needs_match():
    best, ranked = pick(CARD, [cand(set_name="151"), cand(set_name="151")])
    assert best is None and len(ranked) == 2


def test_wrong_set_not_accepted():
    best, ranked = pick(CARD, [cand(set_name="Pokemon Obsidian Flames")])
    assert best is None


def test_no_hits():
    assert pick(CARD, []) == (None, [])
