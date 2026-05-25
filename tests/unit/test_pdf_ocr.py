"""Tests for the OCR fallback. These tests use real Tesseract; if not
installed on the host they skip automatically."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont

from aido.pdf.ocr import OcrStatus, ocr_text

TESSERACT_AVAILABLE = shutil.which("tesseract") is not None
POPPLER_AVAILABLE = shutil.which("pdftoppm") is not None

requires_ocr = pytest.mark.skipif(
    not (TESSERACT_AVAILABLE and POPPLER_AVAILABLE),
    reason="tesseract or poppler not on PATH (`brew install tesseract tesseract-lang poppler`)",
)


def _make_image_only_pdf(target: Path, lines: list[str]) -> Path:
    """Build a PDF whose page is a rasterised image of the given text — no
    embedded text layer, like a scanner would produce."""
    img = Image.new("RGB", (1240, 1754), "white")  # A4 @ 150 dpi
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 36)
    except OSError:
        font = ImageFont.load_default()
    y = 80
    for line in lines:
        draw.text((80, y), line, fill="black", font=font)
        y += 60
    img_path = target.with_suffix(".png")
    img.save(img_path)
    pdf = FPDF(unit="pt", format=(595, 842))
    pdf.add_page()
    pdf.image(str(img_path), x=0, y=0, w=595, h=842)
    target.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(target))
    img_path.unlink(missing_ok=True)
    return target


@requires_ocr
def test_ocr_extracts_text_from_image_only_pdf(tmp_path: Path) -> None:
    pdf = _make_image_only_pdf(tmp_path / "scan.pdf", ["Rechnung Telekom", "Betrag: 49,99 EUR"])
    text, status = ocr_text(pdf)
    assert status is OcrStatus.OK
    # Tesseract isn't perfect — assert key substrings appear
    lc = text.lower()
    assert "rechnung" in lc
    assert "telekom" in lc


@requires_ocr
def test_ocr_returns_empty_for_blank_image_pdf(tmp_path: Path) -> None:
    pdf = _make_image_only_pdf(tmp_path / "blank.pdf", [])
    text, status = ocr_text(pdf)
    assert status is OcrStatus.EMPTY
    assert text == ""


def test_ocr_returns_unavailable_for_garbage_file(tmp_path: Path) -> None:
    # This test runs even without tesseract installed because pdf2image raises
    # early on the bad input.
    p = tmp_path / "garbage.pdf"
    p.write_bytes(b"not a pdf")
    text, status = ocr_text(p)
    assert status is OcrStatus.UNAVAILABLE
    assert text == ""
