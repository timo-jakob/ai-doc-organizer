"""OCR fallback for image-only PDFs.

Uses pdf2image (backed by poppler/pdftoppm) to rasterise each page and
pytesseract to extract text.  Called by the pipeline when pypdf reports
NO_TEXT — i.e. the PDF parsed fine but had no embedded text layer (typical
of stand-alone scanner output).
"""
from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path

_log = logging.getLogger("aido.ocr")

DEFAULT_LANG = "deu+eng"


class OcrStatus(str, Enum):
    OK = "ok"
    EMPTY = "empty"          # OCR ran but found no text
    UNAVAILABLE = "unavailable"  # tesseract/poppler missing, or PDF unreadable


def ocr_text(
    path: Path,
    *,
    lang: str = DEFAULT_LANG,
    max_chars: int = 6 * 1024,
    dpi: int = 200,
) -> tuple[str, OcrStatus]:
    """Rasterise *path* and OCR each page.

    Returns ``(text, status)`` where *text* is truncated to *max_chars*.

    Status meanings:
    - ``OK``: at least one non-whitespace character recognised.
    - ``EMPTY``: OCR completed but yielded only whitespace.
    - ``UNAVAILABLE``: pdf2image or tesseract raised an exception (tools
      missing, corrupt PDF, etc.).  The exception is logged at WARNING level.
    """
    try:
        from pdf2image import convert_from_path  # type: ignore[import-untyped]
        import pytesseract  # type: ignore[import-untyped]

        images = convert_from_path(path, dpi=dpi, fmt="png")
        parts: list[str] = []
        total = 0
        for image in images:
            page_text: str = pytesseract.image_to_string(image, lang=lang)
            if page_text:
                parts.append(page_text)
                total += len(page_text)
                if total >= max_chars:
                    break
    except Exception as exc:
        _log.warning(
            "pipeline.ocr_unavailable",
            extra={"source_path": str(path), "error": str(exc)},
        )
        return "", OcrStatus.UNAVAILABLE

    text = "\n".join(parts)[:max_chars]
    if not text.strip():
        return "", OcrStatus.EMPTY
    return text, OcrStatus.OK
