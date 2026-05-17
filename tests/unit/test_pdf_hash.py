from pathlib import Path

from aido.pdf.hash import sha256_of_file
from tests.fixtures import synth_pdf


def test_sha256_is_stable(tmp_path: Path):
    a = tmp_path / "a.pdf"
    a.write_bytes(b"hello aido")
    assert sha256_of_file(a) == sha256_of_file(a)


def test_sha256_differs_for_different_content(tmp_path: Path):
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    a.write_bytes(b"hello aido")
    b.write_bytes(b"hello aido!")
    assert sha256_of_file(a) != sha256_of_file(b)


def test_synth_pdf_creates_readable_pdf(tmp_path: Path):
    p = synth_pdf(tmp_path / "invoice.pdf", text=["Rechnung", "Telekom GmbH", "100,00 EUR"])
    assert p.exists()
    assert p.read_bytes().startswith(b"%PDF-")
