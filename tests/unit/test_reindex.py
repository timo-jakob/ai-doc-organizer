"""Unit tests for aido.reindex (the `aido rebuild-index` reconciliation)."""

from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from aido.reindex import (
    DISCOVERED_REASONING,
    ReconcileError,
    reconcile,
)
from aido.store.connection import connect
from aido.store.decisions import NewDecision, get_decision, insert_decision, list_recent
from aido.store.migrations import init_db
from aido.store.persons import create_person
from aido.store.taxonomy import create_category
from aido.types import DecisionStatus


@pytest.fixture
def env(tmp_path: Path):
    """An initialized DB (timo/anna/shared + categories) and an archive root."""
    db = tmp_path / "aido.sqlite"
    archive = tmp_path / "archive"
    archive.mkdir()
    with connect(db) as conn:
        init_db(conn)
        persons = {
            slug: create_person(conn, slug=slug, display_name=slug.title(), is_shared=shared)
            for slug, shared in [("timo", False), ("anna", False), ("shared", True)]
        }
        cats = {
            slug: create_category(conn, slug=slug, display_name=slug.title())
            for slug in ["rechnungen", "medizin", "vertraege"]
        }
        cats["_review"] = create_category(
            conn, slug="_review", display_name="_review", is_review=True
        )
        yield conn, archive, persons, cats


def _pdf(archive: Path, rel: str, content: bytes) -> Path:
    p = archive / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"%PDF-1.4\n" + content)
    return p


def _decision_row(person_id: int, category_id: int, filed: Path, hash_: str) -> NewDecision:
    return NewDecision(
        created_at=datetime(2026, 5, 17, 10, tzinfo=UTC),
        source_hash=hash_,
        source_path=f"/inbox/{filed.name}",
        filed_path=str(filed),
        person_id=person_id,
        category_id=category_id,
        doctype_id=None,
        document_date=None,
        counterparty=None,
        proposed_filename=filed.name,
        overall_confidence=0.9,
        person_confidence=0.9,
        category_confidence=0.9,
        reasoning="classified",
        classifier_model="claude-sonnet-5",
        new_category_proposal=None,
        needs_review=False,
        status=DecisionStatus.AUTO_FILED,
    )


def test_discovers_pdf_and_resolves_person_category_from_path(env):
    conn, archive, persons, cats = env
    _pdf(archive, "timo/rechnungen/2026-03-12_stadtwerke-muenchen_rechnung.pdf", b"stadtwerke")

    summary = reconcile(conn, archive)

    assert (summary.added, summary.flagged, summary.in_sync) == (1, 0, 0)
    rows = list_recent(conn, limit=10)
    assert len(rows) == 1
    row = rows[0]
    assert row.status is DecisionStatus.HUMAN_FILED
    assert row.reasoning == DISCOVERED_REASONING
    assert row.person_id == persons["timo"].id
    assert row.category_id == cats["rechnungen"].id
    assert row.needs_review is False
    assert row.proposed_filename == "2026-03-12_stadtwerke-muenchen_rechnung.pdf"
    assert row.classifier_model == "rebuild-index"


def test_fully_in_sync_archive_changes_nothing(env):
    conn, archive, persons, cats = env
    filed = _pdf(archive, "anna/medizin/2026-01-08_dr-mueller_arztbrief.pdf", b"arztbrief")
    insert_decision(conn, _decision_row(persons["anna"].id, cats["medizin"].id, filed, "h1"))
    before = conn.execute("SELECT * FROM decisions ORDER BY id").fetchall()

    summary = reconcile(conn, archive)

    assert (summary.added, summary.flagged, summary.in_sync) == (0, 0, 1)
    after = conn.execute("SELECT * FROM decisions ORDER BY id").fetchall()
    assert [tuple(r) for r in before] == [tuple(r) for r in after]


def test_orphaned_row_is_flagged_failed(env):
    conn, archive, persons, cats = env
    kept = _pdf(archive, "anna/medizin/2026-01-08_dr-mueller_arztbrief.pdf", b"arztbrief")
    kept2 = _pdf(archive, "timo/rechnungen/2026-03-12_stadtwerke_rechnung.pdf", b"stadtwerke")
    gone = archive / "shared/vertraege/2025-11-02_telekom_vertrag.pdf"
    insert_decision(conn, _decision_row(persons["anna"].id, cats["medizin"].id, kept, "h1"))
    insert_decision(conn, _decision_row(persons["timo"].id, cats["rechnungen"].id, kept2, "h2"))
    orphan_id = insert_decision(
        conn, _decision_row(persons["shared"].id, cats["vertraege"].id, gone, "h3")
    )

    summary = reconcile(conn, archive)

    assert (summary.added, summary.flagged, summary.in_sync) == (0, 1, 2)
    assert get_decision(conn, orphan_id).status is DecisionStatus.FAILED


def test_already_failed_row_is_not_reflagged(env):
    conn, archive, persons, cats = env
    kept = _pdf(archive, "anna/medizin/2026-01-08_dr-mueller_arztbrief.pdf", b"arztbrief")
    gone = archive / "shared/vertraege/2025-11-02_telekom_vertrag.pdf"
    insert_decision(conn, _decision_row(persons["anna"].id, cats["medizin"].id, kept, "h1"))
    failed = _decision_row(persons["shared"].id, cats["vertraege"].id, gone, "h3")
    insert_decision(
        conn,
        NewDecision(**{**failed.__dict__, "status": DecisionStatus.FAILED}),
    )

    summary = reconcile(conn, archive)

    assert (summary.added, summary.flagged, summary.in_sync) == (0, 0, 1)


def test_rerun_is_idempotent(env):
    conn, archive, _persons, _cats = env
    _pdf(archive, "timo/rechnungen/2026-03-12_stadtwerke-muenchen_rechnung.pdf", b"stadtwerke")

    first = reconcile(conn, archive)
    second = reconcile(conn, archive)

    assert (first.added, first.flagged) == (1, 0)
    assert (second.added, second.flagged, second.in_sync) == (0, 0, 1)


def test_mass_flag_guard_aborts_without_mutation(env):
    conn, archive, persons, cats = env
    kept = _pdf(archive, "anna/medizin/2026-01-08_dr-mueller_arztbrief.pdf", b"arztbrief")
    insert_decision(conn, _decision_row(persons["anna"].id, cats["medizin"].id, kept, "h1"))
    for i, name in enumerate(["telekom_vertrag", "stadtwerke_rechnung"]):
        insert_decision(
            conn,
            _decision_row(
                persons["shared"].id,
                cats["vertraege"].id,
                archive / f"shared/vertraege/2025-11-0{i + 2}_{name}.pdf",
                f"gone-{i}",
            ),
        )
    before = conn.execute("SELECT * FROM decisions ORDER BY id").fetchall()

    with pytest.raises(ReconcileError, match="mis-mounted or half-synced"):
        reconcile(conn, archive)

    after = conn.execute("SELECT * FROM decisions ORDER BY id").fetchall()
    assert [tuple(r) for r in before] == [tuple(r) for r in after]


def test_exactly_half_flagged_is_allowed(env):
    conn, archive, persons, cats = env
    kept = _pdf(archive, "anna/medizin/2026-01-08_dr-mueller_arztbrief.pdf", b"arztbrief")
    gone = archive / "shared/vertraege/2025-11-02_telekom_vertrag.pdf"
    insert_decision(conn, _decision_row(persons["anna"].id, cats["medizin"].id, kept, "h1"))
    insert_decision(conn, _decision_row(persons["shared"].id, cats["vertraege"].id, gone, "h2"))

    summary = reconcile(conn, archive)  # 1 of 2 = 50%, not "more than 50%"

    assert (summary.added, summary.flagged, summary.in_sync) == (0, 1, 1)


def test_guard_denominator_includes_already_failed_rows(env):
    """Spec-pinned (#4): the >50% guard counts ALL existing rows, including
    already-failed ones. One fresh orphan out of two total rows is exactly
    50% — allowed — even though the other row is a failed one whose file is
    also gone; excluding failed rows from the denominator would wrongly abort."""
    conn, archive, persons, cats = env
    gone_live = archive / "shared/vertraege/2025-11-02_telekom_vertrag.pdf"
    gone_failed = archive / "timo/rechnungen/2025-10-01_alte_rechnung.pdf"
    live_id = insert_decision(
        conn, _decision_row(persons["shared"].id, cats["vertraege"].id, gone_live, "h1")
    )
    failed = _decision_row(persons["timo"].id, cats["rechnungen"].id, gone_failed, "h2")
    insert_decision(conn, NewDecision(**{**failed.__dict__, "status": DecisionStatus.FAILED}))

    summary = reconcile(conn, archive)

    assert (summary.added, summary.flagged, summary.in_sync) == (0, 1, 0)
    assert get_decision(conn, live_id).status is DecisionStatus.FAILED


def test_symlinked_pdf_is_not_indexed(env, tmp_path):
    """A symlink to a PDF outside archive_root must not create a row."""
    conn, archive, _persons, _cats = env
    outside = tmp_path / "private" / "2026-06-01_privat_arztbrief.pdf"
    outside.parent.mkdir(parents=True)
    outside.write_bytes(b"%PDF-1.4\nprivat")
    link_dir = archive / "timo" / "rechnungen"
    link_dir.mkdir(parents=True)
    (link_dir / "geklaut.pdf").symlink_to(outside)

    summary = reconcile(conn, archive)

    assert (summary.added, summary.flagged, summary.in_sync) == (0, 0, 0)
    assert conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 0


def test_missing_archive_root_raises_before_touching_db(env, tmp_path):
    conn, _archive, _persons, _cats = env
    with pytest.raises(ReconcileError, match="not a directory"):
        reconcile(conn, tmp_path / "does-not-exist")


def test_moved_file_relinks_existing_row_instead_of_inserting(env):
    conn, archive, persons, cats = env
    old = _pdf(archive, "timo/rechnungen/2026-03-12_stadtwerke_rechnung.pdf", b"stadtwerke")
    from aido.pdf.hash import sha256_of_file

    decision_id = insert_decision(
        conn, _decision_row(persons["timo"].id, cats["rechnungen"].id, old, sha256_of_file(old))
    )
    new = archive / "timo/nebenkosten-neu" / old.name
    new.parent.mkdir(parents=True)
    old.rename(new)

    summary = reconcile(conn, archive)

    assert (summary.added, summary.flagged, summary.in_sync) == (0, 0, 1)
    assert get_decision(conn, decision_id).filed_path == str(new)


def test_duplicate_content_is_skipped_with_warning(env):
    conn, archive, persons, cats = env
    filed = _pdf(archive, "anna/medizin/2026-01-08_dr-mueller_arztbrief.pdf", b"arztbrief")
    from aido.pdf.hash import sha256_of_file

    insert_decision(
        conn, _decision_row(persons["anna"].id, cats["medizin"].id, filed, sha256_of_file(filed))
    )
    copy = _pdf(archive, "shared/briefe-kopie/arztbrief-kopie.pdf", b"arztbrief")

    summary = reconcile(conn, archive)

    assert (summary.added, summary.flagged, summary.in_sync) == (0, 0, 1)
    assert summary.skipped_duplicates == (str(copy),)


def test_two_identical_new_files_insert_only_one_row(env):
    conn, archive, _persons, _cats = env
    _pdf(archive, "timo/rechnungen/2026-03-12_stadtwerke_rechnung.pdf", b"same-content")
    dup = _pdf(
        archive, "timo/steuer-kopie/2026-03-12_stadtwerke_rechnung_kopie.pdf", b"same-content"
    )

    summary = reconcile(conn, archive)

    assert summary.added == 1
    assert summary.skipped_duplicates == (str(dup),)


def test_unresolvable_path_falls_back_to_shared_and_review(env):
    conn, archive, persons, cats = env
    _pdf(archive, "_review/2026-04-01_unbekannt.pdf", b"unbekannt")
    _pdf(archive, "irgendwo.pdf", b"lose datei")

    summary = reconcile(conn, archive)

    assert summary.added == 2
    rows = list_recent(conn, limit=10)
    by_name = {r.proposed_filename: r for r in rows}
    review_row = by_name["2026-04-01_unbekannt.pdf"]
    assert review_row.category_id == cats["_review"].id
    assert review_row.person_id == persons["shared"].id
    loose_row = by_name["irgendwo.pdf"]
    assert loose_row.category_id == cats["_review"].id
    assert loose_row.person_id == persons["shared"].id


def test_inactive_category_folder_still_resolves_from_layout(env):
    conn, archive, persons, _cats = env
    inactive = create_category(conn, slug="alt", display_name="Alt", is_active=False)
    _pdf(archive, "timo/alt/2026-01-01_altes-dokument.pdf", b"altes dokument")

    summary = reconcile(conn, archive)

    assert summary.added == 1
    row = list_recent(conn, limit=1)[0]
    assert row.person_id == persons["timo"].id
    assert row.category_id == inactive.id


def test_symlinked_archive_root_reports_in_sync_not_duplicate(env, tmp_path):
    conn, archive, persons, cats = env
    filed = _pdf(archive, "anna/medizin/2026-01-08_dr-mueller_arztbrief.pdf", b"arztbrief")
    from aido.pdf.hash import sha256_of_file

    insert_decision(
        conn, _decision_row(persons["anna"].id, cats["medizin"].id, filed, sha256_of_file(filed))
    )
    link = tmp_path / "archive-link"
    link.symlink_to(archive)

    summary = reconcile(conn, link)

    assert (summary.added, summary.flagged, summary.in_sync) == (0, 0, 1)
    assert summary.skipped_duplicates == ()


def test_case_variant_spelling_is_in_sync_not_duplicate(env):
    """A case-only manual rename on a case-insensitive filesystem must not
    misreport the indexed file as a duplicate of itself."""
    conn, archive, persons, cats = env
    filed = _pdf(archive, "anna/medizin/2026-01-08_dr-mueller_arztbrief.pdf", b"arztbrief")
    variant = archive / "Anna" / "medizin" / filed.name
    if not variant.is_file():
        pytest.skip("case-sensitive filesystem")
    from aido.pdf.hash import sha256_of_file

    insert_decision(
        conn, _decision_row(persons["anna"].id, cats["medizin"].id, variant, sha256_of_file(filed))
    )

    summary = reconcile(conn, archive)

    assert (summary.added, summary.flagged, summary.in_sync) == (0, 0, 1)
    assert summary.skipped_duplicates == ()


def test_no_persons_in_db_raises_without_mutation(tmp_path: Path):
    db = tmp_path / "aido.sqlite"
    archive = tmp_path / "archive"
    archive.mkdir()
    _pdf(archive, "timo/rechnungen/2026-03-12_rechnung.pdf", b"rechnung")
    with connect(db) as conn:
        init_db(conn)
        with pytest.raises(ReconcileError, match="run 'aido init'"):
            reconcile(conn, archive)
        assert conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 0


def test_write_failure_rolls_back_everything(env, monkeypatch):
    conn, archive, persons, cats = env
    gone = archive / "shared/vertraege/2025-11-02_telekom_vertrag.pdf"
    kept = _pdf(archive, "anna/medizin/2026-01-08_dr-mueller_arztbrief.pdf", b"arztbrief")
    insert_decision(conn, _decision_row(persons["anna"].id, cats["medizin"].id, kept, "h1"))
    orphan_id = insert_decision(
        conn, _decision_row(persons["shared"].id, cats["vertraege"].id, gone, "h2")
    )
    _pdf(archive, "timo/rechnungen/2026-03-12_stadtwerke_rechnung.pdf", b"stadtwerke")

    def boom(conn_, decision):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr("aido.reindex.insert_decision", boom)
    with pytest.raises(sqlite3.OperationalError):
        reconcile(conn, archive)

    # The orphan flag that ran before the failing insert must be rolled back.
    assert get_decision(conn, orphan_id).status is DecisionStatus.AUTO_FILED


def test_unreadable_archive_root_raises(env, tmp_path):
    conn, _archive, _persons, _cats = env
    locked = tmp_path / "locked-archive"
    locked.mkdir()
    locked.chmod(0o000)
    try:
        if os.access(locked, os.R_OK | os.X_OK):
            pytest.skip("running with privileges that ignore file modes")
        with pytest.raises(ReconcileError, match="not readable"):
            reconcile(conn, locked)
    finally:
        locked.chmod(0o755)


def test_unreadable_pdf_is_skipped_with_warning(env):
    conn, archive, _persons, _cats = env
    readable = _pdf(archive, "timo/rechnungen/2026-03-12_stadtwerke_rechnung.pdf", b"stadtwerke")
    locked = _pdf(archive, "anna/medizin/2026-01-08_dr-mueller_arztbrief.pdf", b"arztbrief")
    locked.chmod(0o000)
    try:
        if os.access(locked, os.R_OK):
            pytest.skip("running with privileges that ignore file modes")
        summary = reconcile(conn, archive)
    finally:
        locked.chmod(0o644)

    assert summary.added == 1
    assert summary.skipped_unreadable == (str(locked),)
    names = {r.proposed_filename for r in list_recent(conn, limit=10)}
    assert names == {readable.name}


def test_failed_row_recovers_when_file_reappears(env):
    conn, archive, persons, cats = env
    filed = _pdf(archive, "anna/medizin/2026-01-08_dr-mueller_arztbrief.pdf", b"arztbrief")
    row = _decision_row(persons["anna"].id, cats["medizin"].id, filed, "h1")
    row_id = insert_decision(conn, NewDecision(**{**row.__dict__, "status": DecisionStatus.FAILED}))

    summary = reconcile(conn, archive)

    assert (summary.added, summary.flagged, summary.recovered) == (0, 0, 1)
    assert get_decision(conn, row_id).status is DecisionStatus.HUMAN_FILED


def test_relinked_failed_row_recovers_to_human_filed(env):
    conn, archive, persons, cats = env
    old = _pdf(archive, "timo/rechnungen/2026-03-12_stadtwerke_rechnung.pdf", b"stadtwerke")
    from aido.pdf.hash import sha256_of_file

    row = _decision_row(persons["timo"].id, cats["rechnungen"].id, old, sha256_of_file(old))
    row_id = insert_decision(conn, NewDecision(**{**row.__dict__, "status": DecisionStatus.FAILED}))
    new = archive / "timo" / "nebenkosten-neu" / old.name
    new.parent.mkdir(parents=True)
    old.rename(new)

    summary = reconcile(conn, archive)

    assert (summary.added, summary.flagged, summary.recovered) == (0, 0, 1)
    updated = get_decision(conn, row_id)
    assert updated.filed_path == str(new)
    assert updated.status is DecisionStatus.HUMAN_FILED


def test_person_folder_without_category_falls_back_to_review(env):
    """A PDF directly under a person folder keeps the person, categorized _review."""
    conn, archive, persons, cats = env
    _pdf(archive, "timo/2026-05-01_lose-rechnung.pdf", b"lose rechnung")

    summary = reconcile(conn, archive)

    assert summary.added == 1
    row = list_recent(conn, limit=1)[0]
    assert row.person_id == persons["timo"].id
    assert row.category_id == cats["_review"].id


def test_missing_review_category_raises_without_mutation(tmp_path: Path):
    db = tmp_path / "aido.sqlite"
    archive = tmp_path / "archive"
    archive.mkdir()
    _pdf(archive, "irgendwo.pdf", b"lose datei")
    with connect(db) as conn:
        init_db(conn)
        create_person(conn, slug="timo", display_name="Timo")
        with pytest.raises(ReconcileError, match="_review category"):
            reconcile(conn, archive)
        assert conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 0


def test_relink_out_of_review_reattributes_and_clears_review_flag(env):
    """Moving a document out of _review by hand re-files it: the row follows
    the new person/category, leaves the review queue, and becomes human_filed."""
    conn, archive, persons, cats = env
    from aido.pdf.hash import sha256_of_file

    moved = _pdf(archive, "timo/rechnungen/2026-03-12_stadtwerke_rechnung.pdf", b"stadtwerke")
    old_review_path = archive / "_review" / "2026-03-12_uncertain_abc123.pdf"
    base = _decision_row(
        persons["shared"].id, cats["_review"].id, old_review_path, sha256_of_file(moved)
    )
    row_id = insert_decision(
        conn,
        NewDecision(
            **{
                **base.__dict__,
                "needs_review": True,
                "status": DecisionStatus.REVIEW,
            }
        ),
    )

    summary = reconcile(conn, archive)

    assert (summary.added, summary.flagged, summary.in_sync) == (0, 0, 1)
    row = get_decision(conn, row_id)
    assert row.filed_path == str(moved)
    assert row.person_id == persons["timo"].id
    assert row.category_id == cats["rechnungen"].id
    assert row.needs_review is False
    assert row.status is DecisionStatus.HUMAN_FILED


def test_relink_to_unresolvable_folder_keeps_attribution(env):
    """A move to a folder that matches no person/category updates only the path."""
    conn, archive, persons, cats = env
    from aido.pdf.hash import sha256_of_file

    old = _pdf(archive, "timo/rechnungen/2026-03-12_stadtwerke_rechnung.pdf", b"stadtwerke")
    row_id = insert_decision(
        conn, _decision_row(persons["timo"].id, cats["rechnungen"].id, old, sha256_of_file(old))
    )
    new = archive / "sortier-mich" / old.name
    new.parent.mkdir(parents=True)
    old.rename(new)

    reconcile(conn, archive)

    row = get_decision(conn, row_id)
    assert row.filed_path == str(new)
    assert row.person_id == persons["timo"].id
    assert row.category_id == cats["rechnungen"].id
    assert row.status is DecisionStatus.AUTO_FILED


def test_relink_into_review_reenters_review_queue(env):
    """Moving a filed document back into _review/ means 're-review this':
    the row must re-enter the review queue, not sit inconsistently filed."""
    conn, archive, persons, cats = env
    from aido.pdf.hash import sha256_of_file

    moved = _pdf(archive, "_review/2026-03-12_stadtwerke_rechnung.pdf", b"stadtwerke")
    old_path = archive / "timo" / "rechnungen" / "2026-03-12_stadtwerke_rechnung.pdf"
    row_id = insert_decision(
        conn,
        _decision_row(persons["timo"].id, cats["rechnungen"].id, old_path, sha256_of_file(moved)),
    )

    summary = reconcile(conn, archive)

    assert (summary.added, summary.flagged, summary.in_sync) == (0, 0, 1)
    row = get_decision(conn, row_id)
    assert row.filed_path == str(moved)
    assert row.category_id == cats["_review"].id
    assert row.needs_review is True
    assert row.status is DecisionStatus.REVIEW


def test_unreadable_row_is_not_relinked_to_content_copy(env):
    """A row whose stored path is merely unreadable must not be re-pointed
    at a same-content copy found elsewhere — the original likely exists."""
    conn, archive, persons, cats = env
    from aido.pdf.hash import sha256_of_file

    locked_dir = archive / "timo" / "steuer-privat"
    hidden = _pdf(archive, "timo/steuer-privat/2026-04-30_steuerbescheid.pdf", b"steuer")
    copy = _pdf(archive, "shared/briefe/steuerbescheid-kopie.pdf", b"steuer")
    row_id = insert_decision(
        conn,
        _decision_row(persons["timo"].id, cats["vertraege"].id, hidden, sha256_of_file(hidden)),
    )
    locked_dir.chmod(0o000)
    try:
        if os.access(hidden, os.R_OK):
            pytest.skip("running with privileges that ignore file modes")
        summary = reconcile(conn, archive)
    finally:
        locked_dir.chmod(0o755)

    assert summary.skipped_duplicates == (str(copy),)
    row = get_decision(conn, row_id)
    assert row.filed_path == str(hidden)
    assert row.status is DecisionStatus.AUTO_FILED


def test_unreadable_row_path_is_not_flagged_failed(env):
    """A stored path that can't be stat'd (permissions) must not fail the row."""
    conn, archive, persons, cats = env
    kept = _pdf(archive, "anna/medizin/2026-01-08_dr-mueller_arztbrief.pdf", b"arztbrief")
    locked_dir = archive / "timo" / "steuer-privat"
    hidden = _pdf(archive, "timo/steuer-privat/2026-04-30_steuerbescheid.pdf", b"steuer")
    insert_decision(conn, _decision_row(persons["anna"].id, cats["medizin"].id, kept, "h1"))
    row_id = insert_decision(
        conn, _decision_row(persons["timo"].id, cats["vertraege"].id, hidden, "h2")
    )
    locked_dir.chmod(0o000)
    try:
        if os.access(hidden, os.R_OK):
            pytest.skip("running with privileges that ignore file modes")
        summary = reconcile(conn, archive)
    finally:
        locked_dir.chmod(0o755)

    assert (summary.added, summary.flagged, summary.in_sync) == (0, 0, 1)
    assert str(hidden) in summary.skipped_unreadable
    assert get_decision(conn, row_id).status is DecisionStatus.AUTO_FILED


def test_uppercase_pdf_extension_is_discovered(env):
    conn, archive, _persons, _cats = env
    _pdf(archive, "timo/rechnungen/2026-03-12_STADTWERKE.PDF", b"stadtwerke")

    summary = reconcile(conn, archive)

    assert summary.added == 1
