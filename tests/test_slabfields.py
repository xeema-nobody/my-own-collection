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


# --- slices 5 + 6: per-grader cert rules, targeted cert reads, grader from the cert length ---
from app.providers.ocr.slabfields import cert_candidates, cert_sure, grader_for_cert  # noqa: E402


def test_cert_sure_follows_each_graders_length_rules():
    assert cert_sure("ACE", "158689") and not cert_sure("ACE", "1586784") and not cert_sure("ACE", "15868")
    assert cert_sure("PSA", "56941091") and cert_sure("PSA", "146737388") and not cert_sure("PSA", "569410917 "[:10])
    assert cert_sure("BGS", "0018969667") and not cert_sure("BGS", "9018969667") and not cert_sure("BGS", "001896966")
    assert cert_sure("CGC", "1234567890") and cert_sure(None, "158689") and not cert_sure(None, "1234567")


def test_targeted_cert_read_outvotes_year_and_number_runs_in_the_label_text():
    lines = ["2023 151 BLASTOISE EX", "FULL ART #184", "9 MINT"]  # "2023 151" joins into a 7 digit run
    assert cert_candidates(lines, None)[0][0] == "2023151"
    got = cert_candidates(lines, "ACE", ["158689", "158689"])
    assert got[0] == ("158689", True)


def test_a_grader_word_that_contradicts_the_cert_length_loses_to_the_length():
    # a logo read as "PSA" on an ACE label: no cert has a PSA length, the 6 digit read is an ACE cert
    lab = parse_label(["PSA", "2023 POKEMON GO", "GEM MINT", "10"], ["158690", "158690"])
    assert (lab.grader, lab.cert, lab.grader_seen, lab.cert_sure) == ("ACE", "158690", False, True)


def test_grader_word_with_a_matching_cert_stays_seen():
    lab = parse_label(["PSA", "MINT 9", "56941091"])
    assert (lab.grader, lab.grader_seen, lab.cert_sure) == ("PSA", True, True)


def test_beckett_cert_with_a_misread_leading_zero_is_repaired_and_the_wrong_read_kept_as_alternative():
    lab = parse_label(["BECKETT", "CENTERING 9 CORNERS 9", "MINT", "9018969667"])
    assert lab.cert == "0018969667" and lab.cert_sure and lab.cert_alt == ("9018969667",)


def test_a_cert_with_no_sure_read_is_flagged_not_guessed():
    lab = parse_label(["PSA", "MINT 9", "5694109"], ["5694109"])
    assert lab.cert == "5694109" and lab.cert_sure is False
    assert lab.as_dict()["cert_sure"] is False
    assert "cert_sure" not in parse_label(["PSA", "MINT 9", "56941091"]).as_dict()


def test_grader_for_cert_by_length_and_prefix():
    assert grader_for_cert([], "158690") == "ACE" and grader_for_cert([], "56941091") == "PSA"
    assert grader_for_cert([], "0016872326") == "BGS" and grader_for_cert([], "4301234567") == "CGC"
    assert grader_for_cert(["CENTERING 9"], "4301234567") == "BGS" and grader_for_cert([], "12345") is None
