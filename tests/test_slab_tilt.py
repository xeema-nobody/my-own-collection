"""label_tilt: finds the rotation that levels text lines (synthetic image, no photos)."""
from PIL import Image, ImageDraw

from app.providers.ocr.slab import label_tilt


def _lines(angle: float) -> Image.Image:
    img = Image.new("L", (1800, 500), 255)
    d = ImageDraw.Draw(img)
    for y in range(60, 460, 70):
        d.rectangle((120, y, 1500, y + 28), fill=20)  # a "text line": a dark bar
    return img.rotate(angle, resample=Image.BICUBIC, fillcolor=255)


def test_level_lines_have_no_tilt():
    assert abs(label_tilt(_lines(0))) <= 0.5


def test_tilt_is_found_both_ways():
    # returns the correction: the angle to pass to Image.rotate to level the label again
    assert abs(label_tilt(_lines(6.0)) + 6.0) <= 1.0
    assert abs(label_tilt(_lines(-8.0)) - 8.0) <= 1.0
