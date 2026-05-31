"""Behavior tests for `aido.worker.pipeline` edge cases.

Covers:
- The outer `try/except` in `process()` returns FAILED on unexpected errors.
- `_process` returns FAILED when the source file vanishes after stabilize.
- `_wait_until_stable` returns once two consecutive sizes match.
- `_route_to_review_no_classify` returns FAILED when the DB has no persons.
- `_record_decision` falls back to a default person when routing produced
  `person_id=None` (UNKNOWN_PERSON path).
"""

from __future__ import annotations

import threading
from datetime import UTC, date, datetime
from unittest.mock import patch

import pytest

from aido.classifier.fake import FakeClassifier
from aido.mutations import MutationContext
from aido.store.connection import connect
from aido.store.decisions import find_by_source_hash
from aido.store.migrations import init_db
from aido.store.persons import create_person
from aido.store.taxonomy import create_category, create_doctype
from aido.types import ClassificationResult, DecisionStatus
from aido.worker.pipeline import Pipeline, PipelineOutcome
from tests.fixtures import synth_empty_pdf, synth_pdf


def _result(**over) -> ClassificationResult:
    base = {
        "person_slug": "timo",
        "category_slug": "rechnungen",
        "doctype_slug": "rechnung",
        "document_date": date(2026, 3, 12),
        "counterparty": "telekom",
        "proposed_filename": "2026-03-12_rechnung_telekom.pdf",
        "overall_confidence": 0.93,
        "person_confidence": 0.95,
        "category_confidence": 0.91,
        "new_category_proposal": None,
        "reasoning": "r",
    }
    base.update(over)
    return ClassificationResult(**base)


@pytest.fixture
def setup(tmp_path):
    """Standard setup: archive + DB seeded with `timo`, `shared`, categories."""
    archive = tmp_path / "archive"
    archive.mkdir()
    with connect(tmp_path / "x.sqlite") as conn:
        init_db(conn)
        create_person(conn, slug="timo", display_name="Timo Jakob")
        create_person(conn, slug="shared", display_name="Shared", is_shared=True)
        create_category(conn, slug="rechnungen", display_name="Rechnungen")
        create_category(conn, slug="_review", display_name="_review", is_review=True)
        create_doctype(conn, slug="rechnung", display_name="Rechnung")
        create_doctype(conn, slug="letter", display_name="Letter")
        mctx = MutationContext(
            conn=conn,
            archive_root=archive,
            lock=threading.Lock(),
            now=lambda: datetime(2026, 5, 17, 10, tzinfo=UTC),
        )
        yield {"conn": conn, "archive": archive, "mctx": mctx, "tmp": tmp_path}


@pytest.fixture
def setup_no_persons(tmp_path):
    """DB with categories but ZERO persons — the failure path for review routing."""
    archive = tmp_path / "archive"
    archive.mkdir()
    with connect(tmp_path / "x.sqlite") as conn:
        init_db(conn)
        # No persons at all.
        create_category(conn, slug="_review", display_name="_review", is_review=True)
        mctx = MutationContext(
            conn=conn,
            archive_root=archive,
            lock=threading.Lock(),
            now=lambda: datetime(2026, 5, 17, 10, tzinfo=UTC),
        )
        yield {"conn": conn, "archive": archive, "mctx": mctx, "tmp": tmp_path}


# ----------------------------------------------------------------------
# process() outer try/except
# ----------------------------------------------------------------------


def test_process_returns_failed_when_internal_call_raises(setup):
    """If something inside `_process` raises an unhandled exception, the
    outer `try/except` in `process()` must catch it and return FAILED.

    `pipeline.py` lines 60-65.
    """
    pdf = synth_pdf(setup["tmp"] / "scan.pdf", text=["doc"])
    pipe = Pipeline(
        conn=setup["conn"],
        classifier=FakeClassifier(results=[_result()]),
        threshold=0.75,
        mutations=setup["mctx"],
        classifier_model="claude-opus-4-7",
        stabilize_seconds=0.0,
    )
    # Force `sha256_of_file` to blow up — exercised inside `_process`, AFTER
    # `_wait_until_stable`. This drops us into the outer except.
    with patch(
        "aido.worker.pipeline.sha256_of_file",
        side_effect=RuntimeError("hash failed"),
    ):
        outcome = pipe.process(pdf)
    assert outcome is PipelineOutcome.FAILED
    # The PDF stays put — we don't delete files we failed on.
    assert pdf.exists()


# ----------------------------------------------------------------------
# Missing source after stabilize
# ----------------------------------------------------------------------


def test_process_returns_failed_when_source_disappears_after_stabilize(setup):
    """If `_wait_until_stable` returns but the file is gone, we must return
    FAILED without classifying.

    `pipeline.py` lines 69-71.
    """
    pdf_path = setup["tmp"] / "vanished.pdf"
    # Don't create the file at all — `_wait_until_stable` short-circuits on
    # FileNotFoundError, then `src.exists()` is False.
    fake = FakeClassifier(results=[])  # must not be called

    pipe = Pipeline(
        conn=setup["conn"],
        classifier=fake,
        threshold=0.75,
        mutations=setup["mctx"],
        classifier_model="claude-opus-4-7",
        stabilize_seconds=0.0,
    )
    outcome = pipe.process(pdf_path)
    assert outcome is PipelineOutcome.FAILED
    assert fake.calls == []


# ----------------------------------------------------------------------
# _wait_until_stable
# ----------------------------------------------------------------------


def test_wait_until_stable_returns_after_two_equal_sizes(setup):
    """`_wait_until_stable` must terminate when two consecutive `stat().st_size`
    calls match. With a static file and a tiny sleep interval, the first iter
    sees size=N (last_size=-1, no match), the second iter sees size=N again
    and returns.

    `pipeline.py` lines 142-152.
    """
    pdf = synth_pdf(setup["tmp"] / "stable.pdf", text=["ready"])
    pipe = Pipeline(
        conn=setup["conn"],
        classifier=FakeClassifier(results=[_result()]),
        threshold=0.75,
        mutations=setup["mctx"],
        classifier_model="claude-opus-4-7",
        stabilize_seconds=0.01,  # small but non-zero to enter the loop
    )
    # No mocking of time.sleep — we want the real loop body executed. The file
    # is static, so two iterations is enough.
    outcome = pipe.process(pdf)
    assert outcome is PipelineOutcome.AUTO_FILED


def test_wait_until_stable_handles_file_not_found(setup):
    """If the file disappears mid-stabilize, FileNotFoundError must be
    caught and the loop exit cleanly. Pipeline then sees the missing file
    in the subsequent `src.exists()` check.

    `pipeline.py` line 153 (`except FileNotFoundError: return`).
    """
    pdf_path = setup["tmp"] / "ghost.pdf"
    pipe = Pipeline(
        conn=setup["conn"],
        classifier=FakeClassifier(results=[]),
        threshold=0.75,
        mutations=setup["mctx"],
        classifier_model="claude-opus-4-7",
        stabilize_seconds=0.01,
    )
    # File doesn't exist → path.stat() raises FileNotFoundError immediately.
    outcome = pipe.process(pdf_path)
    assert outcome is PipelineOutcome.FAILED  # the later src.exists() check


# ----------------------------------------------------------------------
# _route_to_review_no_classify: no person in DB
# ----------------------------------------------------------------------


def test_review_routing_returns_failed_when_db_has_no_persons(setup_no_persons):
    """When extraction fails and the DB has neither a 'shared' person nor
    any other persons, the pipeline must log an error and return FAILED
    rather than crashing on a foreign-key insert.

    `pipeline.py` lines 192-198.
    """
    pdf = synth_empty_pdf(setup_no_persons["tmp"] / "blank.pdf")
    fake = FakeClassifier(results=[])  # classifier never called for empty PDFs

    pipe = Pipeline(
        conn=setup_no_persons["conn"],
        classifier=fake,
        threshold=0.75,
        mutations=setup_no_persons["mctx"],
        classifier_model="claude-opus-4-7",
        stabilize_seconds=0.0,
    )
    outcome = pipe.process(pdf)
    assert outcome is PipelineOutcome.FAILED
    # No decision row should have been created.
    rows = setup_no_persons["conn"].execute("SELECT COUNT(*) AS n FROM decisions").fetchone()
    assert rows["n"] == 0


# ----------------------------------------------------------------------
# _record_decision: fallback person when routing returns person_id=None
# ----------------------------------------------------------------------


def test_record_decision_uses_shared_fallback_when_person_unknown(setup):
    """The classifier produces an unknown person_slug. Routing returns
    REVIEW with `person_id=None`. `_record_decision` must fall back to the
    'shared' person to satisfy the FK constraint, and store the decision.

    `pipeline.py` lines 245-249.
    """
    pdf = synth_pdf(setup["tmp"] / "mystery.pdf", text=["Mystery doc"])
    result = _result(person_slug="not-a-real-person")
    fake = FakeClassifier(results=[result])

    pipe = Pipeline(
        conn=setup["conn"],
        classifier=fake,
        threshold=0.75,
        mutations=setup["mctx"],
        classifier_model="claude-opus-4-7",
        stabilize_seconds=0.0,
    )
    from aido.pdf.hash import sha256_of_file

    pdf_hash = sha256_of_file(pdf)
    outcome = pipe.process(pdf)
    assert outcome is PipelineOutcome.REVIEW

    decision = find_by_source_hash(setup["conn"], pdf_hash)
    assert decision is not None
    assert decision.status is DecisionStatus.REVIEW
    # The fallback person is 'shared' (created in fixture).
    shared_row = setup["conn"].execute("SELECT id FROM persons WHERE slug = 'shared'").fetchone()
    assert decision.person_id == shared_row["id"]
    # Reasoning should be prefixed with the routing reason.
    assert decision.reasoning is not None
    assert "unknown_person" in decision.reasoning


def test_record_decision_uses_any_person_when_shared_missing(setup):
    """If 'shared' doesn't exist, `_any_person()` must supply a fallback.

    Confirms the `get_person_by_slug(...) or self._any_person()` chain.
    """
    # Remove 'shared' so the fallback path uses _any_person().
    setup["conn"].execute("DELETE FROM persons WHERE slug = 'shared'")
    setup["conn"].commit()

    pdf = synth_pdf(setup["tmp"] / "mystery2.pdf", text=["Mystery doc 2"])
    result = _result(person_slug="not-a-real-person")
    fake = FakeClassifier(results=[result])

    pipe = Pipeline(
        conn=setup["conn"],
        classifier=fake,
        threshold=0.75,
        mutations=setup["mctx"],
        classifier_model="claude-opus-4-7",
        stabilize_seconds=0.0,
    )
    from aido.pdf.hash import sha256_of_file

    pdf_hash = sha256_of_file(pdf)
    outcome = pipe.process(pdf)
    assert outcome is PipelineOutcome.REVIEW

    decision = find_by_source_hash(setup["conn"], pdf_hash)
    assert decision is not None
    # Only 'timo' remains as a possible fallback.
    timo_row = setup["conn"].execute("SELECT id FROM persons WHERE slug = 'timo'").fetchone()
    assert decision.person_id == timo_row["id"]
