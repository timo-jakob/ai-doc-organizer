"""Helpers for generating in-test PDF fixtures.

Uses fpdf2 (dev dep) so we don't ship binary fixtures in the repo.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from fpdf import FPDF


def synth_pdf(target: Path, *, text: Sequence[str] = ("Test document",)) -> Path:
    """Create a minimal one-page PDF containing the given lines of text."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    for line in text:
        pdf.cell(0, 10, line, ln=1)
    target.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(target))
    return target


def synth_empty_pdf(target: Path) -> Path:
    """Create a PDF with no text content (a blank page)."""
    pdf = FPDF()
    pdf.add_page()
    target.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(target))
    return target
