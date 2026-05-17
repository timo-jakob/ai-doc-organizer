# tests/unit/test_pipeline.py
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from aido.classifier.fake import FakeClassifier
from aido.mutations import MutationContext
from aido.store.connection import connect
from aido.store.decisions import find_by_source_hash, get_decision
from aido.store.migrations import init_db
from aido.store.persons import create_person
from aido.store.taxonomy import create_category, create_doctype
from aido.types import ClassificationResult, DecisionStatus
from aido.worker.pipeline import PipelineOutcome, Pipeline
from tests.fixtures import synth_empty_pdf, synth_pdf


def _result(**over) -> ClassificationResult:
    base = dict(
        person_slug="timo",
        category_slug="rechnungen",
        doctype_slug="rechnung",
        document_date=date(2026, 3, 12),
        counterparty="telekom",
        proposed_filename="2026-03-12_rechnung_telekom.pdf",
        overall_confidence=0.93,
        person_confidence=0.95,
        category_confidence=0.91,
        new_category_proposal=None,
        reasoning="r",
    )
    base.update(over)
    return ClassificationResult(**base)


@pytest.fixture
def setup(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    with connect(tmp_path / "x.sqlite") as conn:
        init_db(conn)
        create_person(conn, slug="timo", display_name="Timo Jakob")
        create_category(conn, slug="rechnungen", display_name="Rechnungen")
        create_category(conn, slug="_review", display_name="_review", is_review=True)
        create_doctype(conn, slug="rechnung", display_name="Rechnung")
        create_doctype(conn, slug="letter", display_name="Letter")
        mctx = MutationContext(
            conn=conn,
            archive_root=archive,
            lock=threading.Lock(),
            now=lambda: datetime(2026, 5, 17, 10, tzinfo=timezone.utc),
        )
        yield {"conn": conn, "archive": archive, "mctx": mctx, "tmp": tmp_path}


def test_high_confidence_auto_files(setup):
    pdf = synth_pdf(setup["tmp"] / "scan001.pdf", text=["Rechnung", "Telekom"])
    pdf_hash = _hash_of(pdf)
    fake = FakeClassifier(results=[_result()])
    pipe = Pipeline(
        conn=setup["conn"],
        classifier=fake,
        threshold=0.75,
        mutations=setup["mctx"],
        classifier_model="claude-opus-4-7",
        stabilize_seconds=0.0,
    )
    outcome = pipe.process(pdf)
    assert outcome == PipelineOutcome.AUTO_FILED
    decision = find_by_source_hash(setup["conn"], pdf_hash)
    assert decision is not None
    assert decision.status == DecisionStatus.AUTO_FILED
    assert Path(decision.filed_path).exists()
    assert not pdf.exists()


def test_low_confidence_routes_to_review(setup):
    pdf = synth_pdf(setup["tmp"] / "scan001.pdf", text=["Rechnung"])
    pdf_hash = _hash_of(pdf)
    fake = FakeClassifier(results=[_result(overall_confidence=0.4)])
    pipe = Pipeline(
        conn=setup["conn"],
        classifier=fake,
        threshold=0.75,
        mutations=setup["mctx"],
        classifier_model="claude-opus-4-7",
        stabilize_seconds=0.0,
    )
    outcome = pipe.process(pdf)
    assert outcome == PipelineOutcome.REVIEW
    decision = find_by_source_hash(setup["conn"], pdf_hash)
    assert decision.status == DecisionStatus.REVIEW
    assert decision.needs_review is True
    assert (setup["archive"] / "_review").exists()


def test_pdf_without_text_routes_to_review(setup):
    pdf = synth_empty_pdf(setup["tmp"] / "blank.pdf")
    fake = FakeClassifier(results=[])  # should never be called
    pipe = Pipeline(
        conn=setup["conn"],
        classifier=fake,
        threshold=0.75,
        mutations=setup["mctx"],
        classifier_model="claude-opus-4-7",
        stabilize_seconds=0.0,
    )
    outcome = pipe.process(pdf)
    assert outcome == PipelineOutcome.REVIEW
    assert fake.calls == []


def test_duplicate_is_skipped(setup):
    pdf = synth_pdf(setup["tmp"] / "scan001.pdf", text=["Rechnung", "Telekom"])
    # First run files it.
    pipe = Pipeline(
        conn=setup["conn"],
        classifier=FakeClassifier(results=[_result()]),
        threshold=0.75,
        mutations=setup["mctx"],
        classifier_model="claude-opus-4-7",
        stabilize_seconds=0.0,
    )
    assert pipe.process(pdf) == PipelineOutcome.AUTO_FILED

    # Second time same content arrives in inbox.
    dup = synth_pdf(setup["tmp"] / "scan002.pdf", text=["Rechnung", "Telekom"])
    outcome = pipe.process(dup)
    assert outcome == PipelineOutcome.DUPLICATE_SKIP
    assert not dup.exists()  # removed from inbox


def test_classifier_exception_routes_to_review(setup):
    pdf = synth_pdf(setup["tmp"] / "scan001.pdf", text=["Hello"])
    pdf_hash = _hash_of(pdf)
    fake = FakeClassifier(results=[RuntimeError("api timeout")])
    pipe = Pipeline(
        conn=setup["conn"],
        classifier=fake,
        threshold=0.75,
        mutations=setup["mctx"],
        classifier_model="claude-opus-4-7",
        stabilize_seconds=0.0,
    )
    outcome = pipe.process(pdf)
    assert outcome == PipelineOutcome.REVIEW
    decision = find_by_source_hash(setup["conn"], pdf_hash)
    assert decision is not None
    assert decision.needs_review is True
    assert "api timeout" in (decision.reasoning or "")


def _hash_of(path: Path) -> str:
    from aido.pdf.hash import sha256_of_file
    return sha256_of_file(path)
