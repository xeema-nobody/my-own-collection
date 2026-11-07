from app.config import settings
from app.providers.ocr.base import CardFields, ImageError, OcrLine, OcrProvider, OcrUnavailable  # noqa: F401


def get_ocr() -> OcrProvider:
    """Picks the configured reader (`OCR_PROVIDER`)."""
    if settings.ocr_provider == "tesseract":
        from app.providers.ocr.tesseract import TesseractOcr
        return TesseractOcr()
    raise ValueError(f"unknown OCR_PROVIDER {settings.ocr_provider!r} (tesseract)")
