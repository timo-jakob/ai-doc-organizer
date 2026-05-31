"""Additional behavior tests for `aido.pdf.extract`.

Covers branches not exercised by `test_pdf_extract.py`:
- Encrypted PDFs are treated as UNREADABLE.
- A per-page extraction exception is swallowed; the document keeps going.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from aido.pdf.extract import ExtractStatus, extract_text
from tests.fixtures import synth_pdf


class _FakePage:
    """Minimal stand-in for a pypdf page object."""

    def __init__(self, text: str | None, *, raises: Exception | None = None) -> None:
        self._text = text
        self._raises = raises

    def extract_text(self) -> str | None:
        if self._raises is not None:
            raise self._raises
        return self._text


class _FakeReader:
    """Minimal stand-in for pypdf.PdfReader."""

    def __init__(self, pages: list[_FakePage], *, is_encrypted: bool = False) -> None:
        self.pages = pages
        self.is_encrypted = is_encrypted


def test_extract_returns_unreadable_when_pdf_is_encrypted(tmp_path: Path) -> None:
    """An encrypted PDF must not leak text and must be flagged UNREADABLE.

    `extract.py` line 37: `if getattr(reader, "is_encrypted", False)`.
    """
    p = synth_pdf(tmp_path / "encrypted.pdf", text=["secret content"])
    with patch(
        "aido.pdf.extract.PdfReader",
        return_value=_FakeReader([_FakePage("secret content")], is_encrypted=True),
    ):
        text, status = extract_text(p)
    assert status is ExtractStatus.UNREADABLE
    assert text == ""


def test_extract_skips_pages_that_raise_and_keeps_other_pages(tmp_path: Path) -> None:
    """A page whose `extract_text()` raises should not abort the document.

    `extract.py` lines 44-47: the `except Exception` around `page.extract_text()`.
    A good page after a bad page must still appear in the result.
    """
    p = synth_pdf(tmp_path / "mixed.pdf", text=["placeholder"])
    pages = [
        _FakePage("clean header"),
        _FakePage(None, raises=RuntimeError("page 2 broken")),
        _FakePage("clean footer"),
    ]
    with patch("aido.pdf.extract.PdfReader", return_value=_FakeReader(pages)):
        text, status = extract_text(p)
    assert status is ExtractStatus.OK
    assert "clean header" in text
    assert "clean footer" in text
    # Crashed page's content must NOT appear in the output.
    assert "page 2 broken" not in text


def test_extract_returns_no_text_when_every_page_raises(tmp_path: Path) -> None:
    """If every page raises, total extracted text is empty → NO_TEXT.

    Reinforces the swallow behavior: an all-failure document is not UNREADABLE
    (the file parsed fine) — it's NO_TEXT.
    """
    p = synth_pdf(tmp_path / "all_bad.pdf", text=["placeholder"])
    pages = [
        _FakePage(None, raises=RuntimeError("boom 1")),
        _FakePage(None, raises=RuntimeError("boom 2")),
    ]
    with patch("aido.pdf.extract.PdfReader", return_value=_FakeReader(pages)):
        text, status = extract_text(p)
    assert status is ExtractStatus.NO_TEXT
    assert text == ""
