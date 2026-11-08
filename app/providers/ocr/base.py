"""OCR provider contract: bytes of an image in, text lines out. Implementations decide how."""
from dataclasses import dataclass
from typing import Protocol


class ImageError(ValueError):
    """The upload is not a readable image (or is too large in pixels)."""


class OcrUnavailable(RuntimeError):
    """The reader itself failed (binary missing, timeout)."""


@dataclass
class OcrLine:
    text: str
    conf: float  # 0-100, mean word confidence
    top: float   # 0 (top of image) .. 1


@dataclass
class CardFields:
    """What the fixed regions of the flat card say. Every field is None when it could not be read."""
    number: str | None = None        # collector number as printed, leading zeros stripped ("127")
    printed_total: int | None = None  # the "182" of "127/182"
    set_code: str | None = None      # "PAR" (upper case, language code removed)
    hp: int | None = None
    flat: bool = False               # True when read from a perspective-corrected card
    votes: int = 0                   # how many reads of the number region agreed on (number, total)


class OcrProvider(Protocol):
    async def read_lines(self, image: bytes) -> list[OcrLine]: ...
