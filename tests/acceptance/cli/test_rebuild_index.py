"""Acceptance tests for `aido rebuild-index` (story #4, test cases #125-#129).

Each test drives the SHIPPED command-line entry point via subprocess — the
interface the Mac-mini archive operator actually touches — against a real
seeded DB and archive tree. Fixture arrangement uses the aido library; the
behaviour under test always runs through the `aido` executable.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from aido.store.connection import connect
from aido.store.decisions import NewDecision, insert_decision
from aido.store.migrations import init_db
from aido.store.persons import create_person
from aido.store.taxonomy import create_category
from aido.types import DecisionStatus

# The built `aido` entry point from the environment running the tests, so a
# stale system-wide install can never shadow the artifact under test.
_AIDO_BIN = Path(sys.executable).with_name("aido")
ENTRY_POINT = str(_AIDO_BIN) if _AIDO_BIN.exists() else "aido"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [ENTRY_POINT, *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


def _write_pdf(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4\n" + content)
    return path


def _insert_row(conn, *, person_id: int, category_id: int, filed: Path, hash_: str) -> None:
    insert_decision(
        conn,
        NewDecision(
            created_at=datetime(2026, 1, 8, 9, tzinfo=UTC),
            source_hash=hash_,
            source_path=f"/scans/inbox/{filed.name}",
            filed_path=str(filed),
            person_id=person_id,
            category_id=category_id,
            doctype_id=None,
            document_date=None,
            counterparty=None,
            proposed_filename=filed.name,
            overall_confidence=0.93,
            person_confidence=0.93,
            category_confidence=0.93,
            reasoning="classified",
            classifier_model="claude-sonnet-5",
            new_category_proposal=None,
            needs_review=False,
            status=DecisionStatus.AUTO_FILED,
        ),
    )


@pytest.fixture
def household(tmp_path: Path):
    """Seeded household DB + archive: anna's arztbrief filed and in sync,
    shared telekom vertrag filed (file may be deleted per test)."""
    db = tmp_path / "aido.sqlite"
    archive = tmp_path / "archive"
    arztbrief = _write_pdf(
        archive / "anna" / "medizin" / "2026-01-08_dr-mueller_arztbrief.pdf", b"arztbrief"
    )
    vertrag = _write_pdf(
        archive / "shared" / "vertraege" / "2025-11-02_telekom_vertrag.pdf", b"telekom"
    )
    with connect(db) as conn:
        init_db(conn)
        ids = {}
        for slug, name, shared in [
            ("timo", "Timo Jakob", False),
            ("anna", "Anna Jakob", False),
            ("shared", "Shared", True),
        ]:
            ids[slug] = create_person(conn, slug=slug, display_name=name, is_shared=shared).id
        cats = {
            slug: create_category(conn, slug=slug, display_name=slug.title()).id
            for slug in ["rechnungen", "medizin", "vertraege"]
        }
        create_category(conn, slug="_review", display_name="_review", is_review=True)
        _insert_row(
            conn,
            person_id=ids["anna"],
            category_id=cats["medizin"],
            filed=arztbrief,
            hash_="h-arzt",
        )
        _insert_row(
            conn,
            person_id=ids["shared"],
            category_id=cats["vertraege"],
            filed=vertrag,
            hash_="h-telekom",
        )
    return db, archive, arztbrief, vertrag


def test_happy_discovers_orphan_pdf(household):
    """tc-happy-discover-orphan-pdf (#125): an on-disk PDF with no row gets a
    synthetic human_filed row and the summary reports it."""
    db, archive, _, _ = household
    _write_pdf(
        archive / "timo" / "rechnungen" / "2026-03-12_stadtwerke-muenchen_rechnung.pdf",
        b"stadtwerke",
    )

    result = _run("rebuild-index", "--db", str(db), "--archive-root", str(archive))

    assert result.returncode == 0, result.stderr
    assert "1 added, 0 flagged, 2 in sync" in result.stdout
    with connect(db) as conn:
        row = conn.execute(
            "SELECT status, reasoning, needs_review FROM decisions WHERE proposed_filename = ?",
            ("2026-03-12_stadtwerke-muenchen_rechnung.pdf",),
        ).fetchone()
    assert row is not None
    assert row["status"] == "human_filed"
    assert row["reasoning"] == "rebuild-index: discovered on disk"


def test_corner_fully_in_sync_archive(household):
    """tc-corner-fully-in-sync (#126): nothing to do, nothing mutated."""
    db, archive, _, _ = household
    before = db.read_bytes()

    result = _run("rebuild-index", "--db", str(db), "--archive-root", str(archive))

    assert result.returncode == 0, result.stderr
    assert "0 added, 0 flagged, 2 in sync" in result.stdout
    assert db.read_bytes() == before


def test_corner_orphan_row_flagged_failed(household):
    """tc-corner-orphan-row-flagged-failed (#127): a manually deleted file's
    row transitions to failed."""
    db, archive, _, vertrag = household
    vertrag.unlink()

    result = _run("rebuild-index", "--db", str(db), "--archive-root", str(archive))

    assert result.returncode == 0, result.stderr
    assert "0 added, 1 flagged, 1 in sync" in result.stdout
    with connect(db) as conn:
        status = conn.execute(
            "SELECT status FROM decisions WHERE source_hash = 'h-telekom'"
        ).fetchone()["status"]
    assert status == "failed"


def test_error_missing_archive_root(household, tmp_path):
    """tc-error-unreadable-archive-root (#128), missing variant: non-zero
    exit, clear message, DB byte-for-byte unchanged."""
    db, _, _, _ = household
    before = db.read_bytes()

    result = _run("rebuild-index", "--db", str(db), "--archive-root", str(tmp_path / "usb-stick"))

    assert result.returncode != 0
    assert "archive root" in result.stderr
    assert db.read_bytes() == before


def test_error_unreadable_archive_root(household, tmp_path):
    """tc-error-unreadable-archive-root (#128), permission variant: an
    existing but unreadable root fails the same way."""
    db, _, _, _ = household
    locked = tmp_path / "locked-archive"
    locked.mkdir()
    locked.chmod(0o000)
    if os.access(locked, os.R_OK | os.X_OK):
        locked.chmod(0o755)
        pytest.skip("running with privileges that ignore file modes")
    before = db.read_bytes()
    try:
        result = _run("rebuild-index", "--db", str(db), "--archive-root", str(locked))
    finally:
        locked.chmod(0o755)

    assert result.returncode != 0
    assert "archive root is not readable" in result.stderr
    assert db.read_bytes() == before


def test_guard_mass_flag_abort(household):
    """tc-guard-mass-flag-abort (#129): an emptied (mis-mounted) archive would
    flag every row — the command refuses and mutates nothing."""
    db, archive, arztbrief, vertrag = household
    arztbrief.unlink()
    vertrag.unlink()
    before = db.read_bytes()

    result = _run("rebuild-index", "--db", str(db), "--archive-root", str(archive))

    assert result.returncode != 0
    assert "mis-mounted or half-synced" in result.stderr
    assert db.read_bytes() == before
