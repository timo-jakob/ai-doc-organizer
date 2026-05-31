"""PDF text extraction using pypdf, with a tri-state outcome."""

from __future__ import annotations

import logging
from enum import StrEnum
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError, PyPdfError

logger = logging.getLogger(__name__)

DEFAULT_MAX_CHARS = 6 * 1024


class ExtractStatus(StrEnum):
    OK = "ok"
    NO_TEXT = "no_text"
    UNREADABLE = "unreadable"


def extract_text(path: Path, *, max_chars: int = DEFAULT_MAX_CHARS) -> tuple[str, ExtractStatus]:
    """Read embedded text from a PDF.

    Returns `(text, status)`. `text` is truncated to `max_chars`. Status:
    - OK: at least one non-whitespace character was extracted.
    - NO_TEXT: file parsed successfully but had no extractable text layer.
    - UNREADABLE: file could not be parsed (corrupt, encrypted, not a PDF).
    """
    try:
        reader = PdfReader(str(path))
    # ruff 0.15.x with target-version=py314 incorrectly rewrites
    # `except (A, B, C):` to `except A, B, C:` (invalid Python 3); fmt: skip prevents it.
    except (PdfReadError, PyPdfError, ValueError, OSError):  # fmt: skip
        return "", ExtractStatus.UNREADABLE

    if getattr(reader, "is_encrypted", False):
        return "", ExtractStatus.UNREADABLE

    parts: list[str] = []
    total = 0
    for page in reader.pages:
        try:
            page_text = page.extract_text() or ""
        except Exception as e:
            # Per-page extraction failure shouldn't abort the whole document.
            logger.warning("PDF page text extraction failed: %s", e)
            continue
        if not page_text:
            continue
        parts.append(page_text)
        total += len(page_text)
        if total >= max_chars:
            break

    text = "\n".join(parts)[:max_chars]
    if not text.strip():
        return "", ExtractStatus.NO_TEXT
    return text, ExtractStatus.OK
