from datetime import date
from pathlib import Path

import pytest

from aido.filing.filename import build_filename, next_available_name


def test_build_basic():
    name = build_filename(date(2026, 3, 12), "rechnung", "telekom")
    assert name == "2026-03-12_rechnung_telekom.pdf"


def test_build_with_special_chars():
    name = build_filename(date(2026, 2, 8), "tax-notice", "Finanzamt München")
    assert name == "2026-02-08_tax-notice_finanzamt-muenchen.pdf"


def test_build_empty_counterparty_falls_back_to_unknown():
    name = build_filename(date(2026, 3, 1), "letter", "")
    assert name == "2026-03-01_letter_unknown.pdf"


def test_build_empty_doctype_falls_back_to_letter():
    name = build_filename(date(2026, 3, 1), "", "telekom")
    assert name == "2026-03-01_letter_telekom.pdf"


def test_build_truncates_when_too_long():
    long_party = "a" * 200
    name = build_filename(date(2026, 3, 1), "rechnung", long_party)
    stem, ext = name.rsplit(".", 1)
    assert ext == "pdf"
    assert len(stem) <= 80


def test_next_available_name_no_collision(tmp_path: Path):
    target = tmp_path / "2026-03-12_rechnung_telekom.pdf"
    assert next_available_name(target) == target


def test_next_available_name_one_collision(tmp_path: Path):
    base = tmp_path / "2026-03-12_rechnung_telekom.pdf"
    base.touch()
    assert next_available_name(base) == tmp_path / "2026-03-12_rechnung_telekom_2.pdf"


def test_next_available_name_multiple_collisions(tmp_path: Path):
    for i in (None, 2, 3):
        suffix = "" if i is None else f"_{i}"
        (tmp_path / f"2026-03-12_rechnung_telekom{suffix}.pdf").touch()
    assert next_available_name(
        tmp_path / "2026-03-12_rechnung_telekom.pdf"
    ) == tmp_path / "2026-03-12_rechnung_telekom_4.pdf"


def test_next_available_name_gives_up_eventually(tmp_path: Path):
    """If we somehow had >1000 collisions, we raise rather than loop forever."""
    base = tmp_path / "x.pdf"
    base.touch()
    for i in range(2, 1002):
        (tmp_path / f"x_{i}.pdf").touch()
    with pytest.raises(FileExistsError):
        next_available_name(base, max_attempts=1000)
