"""Integration tests for `aido rebuild-index` (CLI wiring around aido.reindex)."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from aido.cli import main as cli_main
from aido.store.connection import connect
from aido.store.decisions import NewDecision, insert_decision, list_recent
from aido.store.migrations import init_db
from aido.store.persons import create_person
from aido.store.taxonomy import create_category
from aido.types import DecisionStatus


@pytest.fixture
def initialized(tmp_path: Path):
    """A seeded DB plus an archive with one filed, in-sync document."""
    db = tmp_path / "aido.sqlite"
    archive = tmp_path / "archive"
    filed = archive / "anna" / "medizin" / "2026-01-08_dr-mueller_arztbrief.pdf"
    filed.parent.mkdir(parents=True)
    filed.write_bytes(b"%PDF-1.4\narztbrief")
    with connect(db) as conn:
        init_db(conn)
        anna = create_person(conn, slug="anna", display_name="Anna Jakob")
        timo = create_person(conn, slug="timo", display_name="Timo Jakob")
        create_person(conn, slug="shared", display_name="Shared", is_shared=True)
        medizin = create_category(conn, slug="medizin", display_name="Medizin")
        create_category(conn, slug="rechnungen", display_name="Rechnungen")
        create_category(conn, slug="_review", display_name="_review", is_review=True)
        insert_decision(
            conn,
            NewDecision(
                created_at=datetime(2026, 1, 8, 9, tzinfo=UTC),
                source_hash="arztbrief-hash",
                source_path="/inbox/scan_0042.pdf",
                filed_path=str(filed),
                person_id=anna.id,
                category_id=medizin.id,
                doctype_id=None,
                document_date=None,
                counterparty="Dr. Müller",
                proposed_filename=filed.name,
                overall_confidence=0.95,
                person_confidence=0.95,
                category_confidence=0.95,
                reasoning="classified",
                classifier_model="claude-sonnet-5",
                new_category_proposal=None,
                needs_review=False,
                status=DecisionStatus.AUTO_FILED,
            ),
        )
    return db, archive, timo.id


def test_rebuild_index_discovers_and_prints_summary(initialized, capsys):
    db, archive, _ = initialized
    new_pdf = archive / "timo" / "rechnungen" / "2026-03-12_stadtwerke-muenchen_rechnung.pdf"
    new_pdf.parent.mkdir(parents=True)
    new_pdf.write_bytes(b"%PDF-1.4\nstadtwerke")

    rc = cli_main(["rebuild-index", "--db", str(db), "--archive-root", str(archive)])

    assert rc == 0
    assert "1 added, 0 flagged, 1 in sync" in capsys.readouterr().out
    with connect(db) as conn:
        statuses = {r.proposed_filename: r.status for r in list_recent(conn, limit=10)}
    assert statuses[new_pdf.name] is DecisionStatus.HUMAN_FILED


def test_rebuild_index_requires_archive_root_flag(initialized, capsys):
    db, _, _ = initialized
    with pytest.raises(SystemExit) as excinfo:
        cli_main(["rebuild-index", "--db", str(db)])
    assert excinfo.value.code == 2
    assert "--archive-root" in capsys.readouterr().err


def test_rebuild_index_missing_archive_root_fails_without_touching_db(initialized, capsys):
    db, archive, _ = initialized
    before = db.read_bytes()

    rc = cli_main(["rebuild-index", "--db", str(db), "--archive-root", str(archive / "nope")])

    assert rc == 1
    assert "not a directory" in capsys.readouterr().err
    assert db.read_bytes() == before


def test_rebuild_index_missing_db_fails(initialized, capsys, tmp_path):
    _, archive, _ = initialized
    missing_db = tmp_path / "missing.sqlite"

    rc = cli_main(["rebuild-index", "--db", str(missing_db), "--archive-root", str(archive)])

    assert rc == 1
    assert "run 'aido init'" in capsys.readouterr().err
    assert not missing_db.exists()


def test_rebuild_index_corrupt_db_fails_cleanly(initialized, capsys, tmp_path):
    """A non-SQLite --db file produces a clear error, not a traceback."""
    _, archive, _ = initialized
    garbage_db = tmp_path / "garbage.sqlite"
    garbage_db.write_bytes(b"this is not a sqlite database, just bytes\n" * 10)

    rc = cli_main(["rebuild-index", "--db", str(garbage_db), "--archive-root", str(archive)])

    assert rc == 1
    assert "rebuild-index: file is not a database" in capsys.readouterr().err


def test_rebuild_index_mass_flag_guard_exits_nonzero(initialized, capsys):
    db, archive, timo_id = initialized
    with connect(db) as conn:
        for i in range(2):
            insert_decision(
                conn,
                NewDecision(
                    created_at=datetime(2025, 11, 2, 8, tzinfo=UTC),
                    source_hash=f"gone-{i}",
                    source_path=f"/inbox/scan_005{i}.pdf",
                    filed_path=str(archive / "timo" / "rechnungen" / f"gone_{i}.pdf"),
                    person_id=timo_id,
                    category_id=1,
                    doctype_id=None,
                    document_date=None,
                    counterparty=None,
                    proposed_filename=f"gone_{i}.pdf",
                    overall_confidence=0.9,
                    person_confidence=0.9,
                    category_confidence=0.9,
                    reasoning="classified",
                    classifier_model="claude-sonnet-5",
                    new_category_proposal=None,
                    needs_review=False,
                    status=DecisionStatus.AUTO_FILED,
                ),
            )

    rc = cli_main(["rebuild-index", "--db", str(db), "--archive-root", str(archive)])

    assert rc == 1
    assert "mis-mounted or half-synced" in capsys.readouterr().err
    with connect(db) as conn:
        failed = conn.execute("SELECT COUNT(*) FROM decisions WHERE status = 'failed'").fetchone()[
            0
        ]
    assert failed == 0


def test_rebuild_index_warns_on_unreadable_pdf(initialized, capsys):
    db, archive, _ = initialized
    locked = archive / "shared" / "briefe" / "unlesbar.pdf"
    locked.parent.mkdir(parents=True)
    locked.write_bytes(b"%PDF-1.4\nunlesbar")
    locked.chmod(0o000)
    try:
        if os.access(locked, os.R_OK):
            pytest.skip("running with privileges that ignore file modes")
        rc = cli_main(["rebuild-index", "--db", str(db), "--archive-root", str(archive)])
    finally:
        locked.chmod(0o644)

    assert rc == 0
    captured = capsys.readouterr()
    assert f"rebuild-index: warning: {locked} is unreadable; skipped" in captured.err
    assert "0 added, 0 flagged, 1 in sync" in captured.out


def test_rebuild_index_reports_recovered_rows(initialized, capsys):
    db, archive, timo_id = initialized
    back = archive / "timo" / "rechnungen" / "2026-02-01_stadtwerke_rechnung.pdf"
    back.parent.mkdir(parents=True)
    back.write_bytes(b"%PDF-1.4\nrechnung")
    with connect(db) as conn:
        insert_decision(
            conn,
            NewDecision(
                created_at=datetime(2026, 2, 1, 8, tzinfo=UTC),
                source_hash="recovered-hash",
                source_path="/inbox/scan_0099.pdf",
                filed_path=str(back),
                person_id=timo_id,
                category_id=1,
                doctype_id=None,
                document_date=None,
                counterparty=None,
                proposed_filename=back.name,
                overall_confidence=0.9,
                person_confidence=0.9,
                category_confidence=0.9,
                reasoning="classified",
                classifier_model="claude-sonnet-5",
                new_category_proposal=None,
                needs_review=False,
                status=DecisionStatus.FAILED,
            ),
        )

    rc = cli_main(["rebuild-index", "--db", str(db), "--archive-root", str(archive)])

    assert rc == 0
    captured = capsys.readouterr()
    assert "rebuild-index: 1 previously-failed row(s) recovered" in captured.err
    assert "0 added, 0 flagged, 2 in sync" in captured.out
    with connect(db) as conn:
        statuses = {r.proposed_filename: r.status for r in list_recent(conn, limit=10)}
    assert statuses[back.name] is DecisionStatus.HUMAN_FILED


def test_rebuild_index_warns_on_duplicate_content(initialized, capsys):
    db, archive, _ = initialized
    copy = archive / "shared" / "briefe-kopie" / "arztbrief-kopie.pdf"
    copy.parent.mkdir(parents=True)
    copy.write_bytes(b"%PDF-1.4\narztbrief")
    # Give the original row the real content hash so the copy collides.
    original = archive / "anna" / "medizin" / "2026-01-08_dr-mueller_arztbrief.pdf"
    from aido.pdf.hash import sha256_of_file

    with connect(db) as conn:
        conn.execute(
            "UPDATE decisions SET source_hash = ? WHERE filed_path = ?",
            (sha256_of_file(original), str(original)),
        )

    rc = cli_main(["rebuild-index", "--db", str(db), "--archive-root", str(archive)])

    assert rc == 0
    captured = capsys.readouterr()
    assert "0 added, 0 flagged, 1 in sync" in captured.out
    assert "duplicates an already-indexed document" in captured.err
