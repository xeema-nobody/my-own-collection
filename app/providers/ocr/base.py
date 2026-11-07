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


class OcrProvider(Protocol):
    async def read_lines(self, image: bytes) -> list[OcrLine]: ...
