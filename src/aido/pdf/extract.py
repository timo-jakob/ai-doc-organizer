"""PDF text extraction using pypdf, with a tri-state outcome."""
from __future__ import annotations

from enum import Enum
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError, PyPdfError

DEFAULT_MAX_CHARS = 6 * 1024


class ExtractStatus(str, Enum):
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
    except (PdfReadError, PyPdfError, ValueError, OSError):
        return "", ExtractStatus.UNREADABLE

    if getattr(reader, "is_encrypted", False):
        return "", ExtractStatus.UNREADABLE

    parts: list[str] = []
    total = 0
    for page in reader.pages:
        try:
            page_text = page.extract_text() or ""
        except Exception:
            # Per-page extraction failure shouldn't abort the whole document.
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
