"""Slab label parsing: pure text in, grader / grade / cert out. Lines are shaped like real tesseract output of the
24 private slab photos (noise, split rows, a subgrade row next to the grade)."""
from app.providers.ocr.slab import pick_grade
from app.providers.ocr.slabfields import parse_label, plausible

PSA = ["2019 POKEMON SUN & MOON", "FA/GRCHMP. & GRTN. GX", "UNIFIED MINDS", "#228", "MINT 9", "56941091", "56941091 i", "569410"]
BGS = ["2024 SCARLET & VIOLET", "#233 GARDEVOIR EX SIR", "CENTERING 9 CORNERS 9", "EDGES 10 SURFACE 10", "9 MINT",
       "0018969667", "001 8969667", "BECKETTS"]
BGS_95 = ["CENTERING 9.5 CORNERS 10", "EDGES 9.5 SURFACE 9.5", "9.5", "GEM MINT", "0016872326"]
ACE = ["2022 POKEMON GO", "RADIANT CHARIZARD", "10", "GEM MINT", "158690", "158690 |", "1586"]
CGC = ["CGC", "2022 STAR BIRTH", "PRISTINE 10", "4001234567"]


def test_psa_by_cert_length_and_grade_next_to_tier():
    r = parse_label(PSA)
    assert (r.grader, r.grade, r.cert, r.tier, r.is_slab) == ("PSA", 9.0, "56941091", "MINT", True)
    assert r.grader_seen is False  # inferred from the layout: the user confirms the chip


def test_beckett_subgrades_are_not_the_grade():
    r = parse_label(BGS)
    assert (r.grader, r.grade, r.cert) == ("BGS", 9.0, "0018969667")
    assert r.grader_seen is True  # the word BECKETT was read


def test_half_grade_and_gem_mint():
    r = parse_label(BGS_95)
    assert (r.grader, r.grade, r.cert, r.tier) == ("BGS", 9.5, "0016872326", "GEM MINT")


def test_ace_has_no_name_on_the_label_six_digit_cert():
    r = parse_label(ACE)
    assert (r.grader, r.grade, r.cert) == ("ACE", 10.0, "158690")
    assert r.grader_seen is False


def test_named_grader_wins_over_layout_guess():
    r = parse_label(CGC)
    assert r.grader == "CGC" and r.grader_seen and r.cert == "4001234567"


def test_cert_vote_prefers_the_most_common_read():
    r = parse_label(["MINT 9", "158687", "158689", "158689"])
    assert r.cert == "158689"


def test_card_text_alone_is_not_a_slab():
    assert parse_label(["BASIC", "Charizard", "HP 120", "Fire Spin 100", "4/102"]).is_slab is False
    assert parse_label([]).is_slab is False


def test_tier_word_limits_the_grade():
    assert plausible("GEM MINT", 10) and plausible("GEM MINT", 9.5) and not plausible("GEM MINT", 4)
    assert plausible("MINT", 9) and not plausible("MINT", 10)
    assert plausible(None, 7)
    # a stray "7" read next to GEM MINT never wins
    assert parse_label(["7", "GEM MINT", "10", "158678"]).grade == 10.0


def test_pick_grade_largest_glyph_then_most_reads():
    assert pick_grade([(9.0, 40), (1.0, 12), (9.0, 38)]) == 9.0
    assert pick_grade([(4.0, 50)], tier="GEM MINT") is None
    assert pick_grade([]) is None
