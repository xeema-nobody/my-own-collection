"""Position-based slab reading: find the slab against a dark table, pick the grade glyph. Synthetic images, no OCR."""
from PIL import Image, ImageDraw

from app.providers.ocr import slab as S


def _photo(slab_box=(200, 150, 600, 850), size=(800, 1000), bg=15):
    img = Image.new("RGB", size, (bg, bg, bg))
    ImageDraw.Draw(img).rectangle(slab_box, fill=(150, 150, 155))
    return img


def test_find_slab_boxes_the_light_blob_on_a_dark_table():
    x0, y0, x1, y1 = S.find_slab(_photo())
    assert abs(x0 - 200) < 25 and abs(x1 - 600) < 25 and abs(y0 - 150) < 25 and abs(y1 - 850) < 25


def test_find_slab_none_on_empty_table_or_a_flat_landscape_blob():
    assert S.find_slab(Image.new("RGB", (800, 1000), (15, 15, 15))) is None
    assert S.find_slab(_photo(slab_box=(50, 300, 750, 600))) is None


def test_zone_is_the_top_of_the_slab_at_a_fixed_width():
    z = S._zone(_photo())
    assert z is not None and z.width == S.ZONE_W
    assert z.height < z.width  # a strip, not the whole slab


def test_pick_grade_prefers_the_big_glyph_and_whole_token_over_a_cut_one():
    assert S.pick_grade([(9.5, 150), (5.0, 154)], "GEM MINT") == 9.5
    assert S.pick_grade([(10.0, 150), (1.0, 150)], "GEM MINT") == 10.0
    assert S.pick_grade([(9.0, 150), (4.0, 20)], "MINT") == 9.0
    assert S.pick_grade([(4.0, 150)], "GEM MINT") is None  # the tier word does not allow a 4


def _slab_photo():
    """Dark table, light slab, a text-like label strip (vertical strokes) near the top, quiet plastic between, art below."""
    img = _photo(slab_box=(200, 150, 600, 850))
    d = ImageDraw.Draw(img)
    for row in range(3):  # three lines of text, 40 px apart, starting 40 px below the slab top
        for x in range(230, 570, 14):
            d.rectangle((x, 190 + row * 40, x + 5, 215 + row * 40), fill=(10, 10, 10))
    for y in range(420, 700, 18):  # card art lower down
        d.rectangle((230, y, 570, y + 8), fill=(200, 60, 60))
    return img


def test_locate_label_finds_the_text_band_near_the_top_of_the_slab():
    img = _slab_photo()
    box = S.find_slab(img)
    lb = S.locate_label(img, box)
    assert lb is not None
    assert 150 <= lb[1] <= 215 and 295 <= lb[3] <= 400  # the three text lines, not the art band
    assert lb[0] >= box[0] and lb[2] <= box[2]


def test_locate_label_none_when_the_first_text_band_starts_too_low():
    img = _photo(slab_box=(200, 150, 600, 850))
    d = ImageDraw.Draw(img)
    for x in range(230, 570, 14):  # only a band at 60 % of the slab: that is card art, not a label
        d.rectangle((x, 600, x + 5, 700), fill=(10, 10, 10))
    assert S.locate_label(img, S.find_slab(img)) is None


def test_merge_fills_a_missing_cert_and_grade_from_the_slow_read():
    from app.providers.ocr.slabfields import SlabLabel
    fast = S.SlabRead(SlabLabel("PSA", None, "5694109", "MINT", True, True, False, ()), ["a"])
    slow = S.SlabRead(SlabLabel("PSA", 9.0, "56941091", "MINT", True, True, True, ()), ["b"])
    m = S._merge(fast, slow).label
    assert (m.cert, m.cert_sure, m.grade) == ("56941091", True, 9.0)
    assert S._merge(None, slow) is slow and S._merge(fast, None) is fast
    keep = S.SlabRead(SlabLabel("PSA", 9.0, "56941091", "MINT", True, True, True, ()), [])
    assert S._merge(keep, S.SlabRead(SlabLabel("PSA", 8.0, "11111111", "MINT", True, True, True, ()), [])).label.cert == "56941091"
