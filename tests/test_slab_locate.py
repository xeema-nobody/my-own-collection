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
