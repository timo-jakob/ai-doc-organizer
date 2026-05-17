from pathlib import Path

from aido.pdf.extract import ExtractStatus, extract_text
from tests.fixtures import synth_empty_pdf, synth_pdf


def test_extract_ok(tmp_path: Path):
    p = synth_pdf(tmp_path / "ok.pdf", text=["Rechnung", "Telekom GmbH"])
    text, status = extract_text(p)
    assert status == ExtractStatus.OK
    assert "Rechnung" in text
    assert "Telekom" in text


def test_extract_no_text_for_blank_pdf(tmp_path: Path):
    p = synth_empty_pdf(tmp_path / "blank.pdf")
    text, status = extract_text(p)
    assert status == ExtractStatus.NO_TEXT
    assert text == ""


def test_extract_unreadable_for_garbage_file(tmp_path: Path):
    p = tmp_path / "garbage.pdf"
    p.write_bytes(b"not a pdf at all")
    text, status = extract_text(p)
    assert status == ExtractStatus.UNREADABLE
    assert text == ""


def test_extract_truncates(tmp_path: Path):
    body = ["Line " + str(i) for i in range(2000)]
    p = synth_pdf(tmp_path / "long.pdf", text=body)
    text, status = extract_text(p, max_chars=1024)
    assert status == ExtractStatus.OK
    assert len(text) <= 1024
