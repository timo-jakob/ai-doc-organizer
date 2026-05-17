from pathlib import Path

import pytest

from aido.filing.executor import FilingTarget, file_document


def test_file_document_moves_into_person_category(tmp_path: Path):
    src = tmp_path / "inbox" / "scan001.pdf"
    src.parent.mkdir()
    src.write_bytes(b"x")
    archive = tmp_path / "archive"
    archive.mkdir()
    target = file_document(
        src,
        archive_root=archive,
        target=FilingTarget(
            person_slug="timo",
            category_slug="rechnungen",
            filename="2026-03-12_rechnung_telekom.pdf",
        ),
    )
    assert target == archive / "timo" / "rechnungen" / "2026-03-12_rechnung_telekom.pdf"
    assert target.exists()
    assert not src.exists()
    assert target.read_bytes() == b"x"


def test_file_document_to_review_uses_top_level(tmp_path: Path):
    src = tmp_path / "inbox" / "s.pdf"
    src.parent.mkdir()
    src.write_bytes(b"y")
    archive = tmp_path / "archive"
    archive.mkdir()
    target = file_document(
        src,
        archive_root=archive,
        target=FilingTarget(person_slug=None, category_slug="_review",
                            filename="2026-03-15_uncertain_low-confidence_unknown.pdf"),
    )
    assert target == archive / "_review" / "2026-03-15_uncertain_low-confidence_unknown.pdf"


def test_collision_appends_suffix(tmp_path: Path):
    archive = tmp_path / "archive"
    target_dir = archive / "timo" / "rechnungen"
    target_dir.mkdir(parents=True)
    (target_dir / "x.pdf").write_bytes(b"existing")

    src = tmp_path / "src.pdf"
    src.write_bytes(b"new")
    out = file_document(
        src,
        archive_root=archive,
        target=FilingTarget(person_slug="timo", category_slug="rechnungen", filename="x.pdf"),
    )
    assert out == target_dir / "x_2.pdf"
    assert out.read_bytes() == b"new"
    assert (target_dir / "x.pdf").read_bytes() == b"existing"


def test_creates_missing_directories(tmp_path: Path):
    src = tmp_path / "src.pdf"
    src.write_bytes(b"x")
    archive = tmp_path / "archive"
    out = file_document(
        src,
        archive_root=archive,
        target=FilingTarget(person_slug="anna", category_slug="medizin",
                            filename="2026-01-19_letter_helios.pdf"),
    )
    assert out.exists()
    assert out.parent == archive / "anna" / "medizin"


def test_file_document_rejects_path_traversal(tmp_path: Path):
    src = tmp_path / "src.pdf"
    src.write_bytes(b"x")
    archive = tmp_path / "archive"
    with pytest.raises(ValueError, match="escapes archive root"):
        file_document(
            src,
            archive_root=archive,
            target=FilingTarget(
                person_slug="..",
                category_slug="..",
                filename="evil.pdf",
            ),
        )
