"""Tesseract provider on synthetic card-name images (rendered here, no real card art in the repo).
Proves the pipeline; accuracy on real phone photos is checked by hand (docs/decisions.md)."""
import io
import shutil

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.providers.ocr import ImageError
from app.providers.ocr.tesseract import TesseractOcr, find_card, parse_tsv, prepare

needs_tesseract = pytest.mark.skipif(not shutil.which("tesseract"), reason="tesseract not installed")


def card_image(name: str, w=630, h=880, fmt="PNG", size=46) -> bytes:
    img = Image.new("RGB", (w, h), (232, 210, 120))
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=size)
    d.text((70, 38), "BASIC", fill=(30, 30, 30), font=ImageFont.load_default(size=22))
    d.text((70, 62), name, fill=(15, 15, 15), font=font)
    d.text((w - 190, 62), "HP 120", fill=(15, 15, 15), font=ImageFont.load_default(size=30))
    d.rectangle((50, 150, w - 50, h - 220), fill=(120, 160, 200))
    buf = io.BytesIO()
    img.save(buf, fmt)
    return buf.getvalue()


def test_prepare_rejects_garbage_and_wrong_formats():
    with pytest.raises(ImageError):
        prepare(b"not an image")
    buf = io.BytesIO()
    Image.new("RGB", (10, 10)).save(buf, "GIF")
    with pytest.raises(ImageError):
        prepare(buf.getvalue())


def test_prepare_is_grayscale_and_caps_the_long_side():
    img = prepare(card_image("Pikachu"))
    assert img.mode == "L" and img.size == (630, 880)
    big = prepare(card_image("Pikachu", w=3000, h=4200))
    assert max(big.size) == 2400 and big.mode == "L"


def table_photo(name: str, card_box=(1000, 1500, 2000, 2900), table=(20, 20, 24), size=64) -> bytes:
    """A phone-style photo: dark table, the card (lit) in the middle, nothing in the top 20 %."""
    img = Image.new("RGB", (3024, 4032), table)
    x0, y0, x1, y1 = card_box
    img.paste(Image.open(io.BytesIO(card_image(name, w=x1 - x0, h=y1 - y0, size=size))), (x0, y0))
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


def test_find_card_boxes_the_lit_card_on_a_dark_table():
    box = find_card(prepare(table_photo("Charizard")))
    assert box is not None
    k = 2400 / 4032  # prepare() downscales the long side
    x0, y0, x1, y1 = (round(v * k) for v in (1000, 1500, 2000, 2900))
    assert abs(box[0] - x0) < 40 and abs(box[1] - y0) < 40 and abs(box[2] - x1) < 40 and abs(box[3] - y1) < 40


def test_find_card_handles_a_light_table_and_gives_up_on_a_blank_frame():
    light = table_photo("Charizard", table=(235, 235, 230))
    img = prepare(light)
    assert find_card(img) is not None  # card (yellow, darker than the table) is still boxed
    flat = Image.new("RGB", (800, 1000), (30, 30, 30))
    assert find_card(prepare(_png(flat))) is None


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


@needs_tesseract
@pytest.mark.parametrize("name", ["Charizard", "Squirtle"])
async def test_reads_a_name_from_a_photo_where_the_top_fifth_is_table(name):
    lines = await TesseractOcr().read_lines(table_photo(name))
    assert name.lower() in " ".join(ln.text for ln in lines).lower()


@needs_tesseract
async def test_stages_yield_cheapest_crop_first_and_the_caller_can_stop():
    seen = 0
    async for lines in TesseractOcr().stages(table_photo("Charizard")):
        seen += 1
        if "charizard" in " ".join(ln.text for ln in lines).lower():
            break
    assert seen == 1  # the first (top band of the located card) already reads it


def test_parse_tsv_groups_words_into_lines():
    head = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
    rows = [head, "5\t1\t1\t1\t1\t1\t0\t20\t5\t5\t90\tHello", "5\t1\t1\t1\t1\t2\t9\t20\t5\t5\t70\tworld",
            "5\t1\t1\t1\t2\t1\t0\t80\t5\t5\t-1\tjunk", "4\t1\t1\t1\t1\t0\t0\t0\t0\t0\t-1\t"]
    lines = parse_tsv("\n".join(rows), 100)
    assert len(lines) == 1 and lines[0].text == "Hello world" and lines[0].conf == 80 and lines[0].top == 0.2


@needs_tesseract
@pytest.mark.parametrize("name", ["Charizard", "Pikachu", "Squirtle"])
async def test_reads_the_name_from_the_top_band(name):
    lines = await TesseractOcr().read_lines(card_image(name))
    assert name.lower() in " ".join(ln.text for ln in lines).lower()


@needs_tesseract
async def test_reads_a_jpeg_photo_too():
    lines = await TesseractOcr().read_lines(card_image("Charizard", fmt="JPEG"))
    assert "charizard" in " ".join(ln.text for ln in lines).lower()
