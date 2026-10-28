from app.services.price_matrix import build_matrix, grades_for, value_of

CARD = {"_id": "pokemon:base1-4", "variants": ["holofoil", "normal"]}
RATES = {"EUR": 1.0, "USD": 0.9, "GBP": None}


def row(grade="raw", source="cardmarket", kind="market", day="2026-10-27", currency="EUR", variant=None, **vals):
    return {"grade_key": grade, "source": source, "kind": kind, "observed_on": day,
            "currency": currency, "variant": variant, **vals}


def cell(rows, grade="raw", source="cardmarket", card=CARD):
    return build_matrix(card, rows, RATES)["cells"][grade][source]


def test_value_of_prefers_market_then_median_then_avg():
    assert value_of({"market": 5, "median": 9, "avg": 1}) == 5
    assert value_of({"median": 9, "avg": 1}) == 9
    assert value_of({"avg": 1}) == 1
    assert value_of({"market": 0}) == 0          # 0 cents is a value, not missing
    assert value_of({"kind": "market", "low": 3}) is None
    assert value_of({"kind": "ask", "low": 3}) == 3


def test_row_without_value_is_ignored_not_zero():
    assert cell([row(market=None)]) is None
    assert cell([]) is None


def test_baseline_grades_and_dynamic_grades_sorted():
    g, graders = grades_for([row(grade="G9"), row(grade="BGS9.5"), row(grade="PSA8"), row(grade="BGS10Black")])
    assert g[0] == "raw"
    assert g.index("G9") < g.index("PSA10") < g.index("BGS10") < g.index("CGC10")  # buckets, then PSA/BGS/CGC
    assert g.index("BGS10") < g.index("BGS10Black") < g.index("BGS9.5") < g.index("BGS9")
    assert graders == ["PSA", "BGS", "CGC"]  # bucket G9 is not a company


def test_unknown_grader_is_listed_after_known_ones():
    g, graders = grades_for([row(grade="TAG10")])
    assert graders == ["PSA", "BGS", "CGC", "TAG"]
    assert g.index("TAG10") > g.index("CGC1")


def test_newest_day_wins_even_over_better_kind():
    c = cell([row(kind="sold", day="2026-10-01", median=900), row(kind="market", day="2026-10-27", market=500)])
    assert (c["kind"], c["price"], c["observed_on"]) == ("market", 500, "2026-10-27")


def test_same_day_sold_beats_market_beats_ask():
    rows = [row(kind="ask", low=100), row(kind="market", market=200), row(kind="sold", median=300)]
    assert cell(rows)["kind"] == "sold"
    assert cell(rows[:2])["kind"] == "market"


def test_same_day_same_kind_first_variant_wins():
    rows = [row(variant="normal", market=100), row(variant="holofoil", market=900), row(variant=None, market=50)]
    c = cell(rows)
    assert c["variant"] is None  # variant-less row ranks first; then card's variant order
    c = cell(rows[:2])
    assert (c["variant"], c["price"]) == ("holofoil", 900)


def test_unknown_variant_ranks_last():
    c = cell([row(variant="reverse", market=1), row(variant="normal", market=2)])
    assert c["variant"] == "normal"


def test_currency_conversion_and_missing_rate():
    c = cell([row(currency="USD", market=1000)])
    assert (c["price"], c["currency"], c["price_base"]) == (1000, "USD", 900)
    c = cell([row(currency="GBP", market=1000)])
    assert (c["price"], c["price_base"]) == (1000, None)


def test_extra_source_from_data_is_appended_and_seed_flag():
    m = build_matrix(CARD, [row(source="manual", market=5, seed=True)], RATES)
    assert m["sources"][-1] == "manual"
    assert m["cells"]["raw"]["manual"]["seed"] is True
    assert m["cells"]["raw"]["cardmarket"] is None
    assert m["card_id"] == CARD["_id"]
