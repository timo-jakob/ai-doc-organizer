"""Verify the pipeline falls back to OCR when pypdf returns NO_TEXT."""
from __future__ import annotations

import threading
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from aido.classifier.fake import FakeClassifier
from aido.mutations import MutationContext
from aido.pdf.ocr import OcrStatus
from aido.store.connection import connect
from aido.store.decisions import find_by_source_hash
from aido.store.migrations import init_db
from aido.store.persons import create_person
from aido.store.taxonomy import create_category, create_doctype
from aido.types import ClassificationResult, DecisionStatus
from aido.worker.pipeline import Pipeline, PipelineOutcome
from tests.fixtures import synth_empty_pdf


def _result() -> ClassificationResult:
    return ClassificationResult(
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
        reasoning="ocr fallback test",
    )


@pytest.fixture
def setup(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    with connect(tmp_path / "x.sqlite") as conn:
        init_db(conn)
        create_person(conn, slug="timo", display_name="Timo")
        create_person(conn, slug="shared", display_name="Shared", is_shared=True)
        create_category(conn, slug="rechnungen", display_name="Rechnungen")
        create_category(conn, slug="_review", display_name="_review", is_review=True)
        create_doctype(conn, slug="rechnung", display_name="Rechnung")
        mctx = MutationContext(
            conn=conn, archive_root=archive, lock=threading.Lock(),
            now=lambda: datetime(2026, 5, 17, 10, tzinfo=timezone.utc),
        )
        yield {"conn": conn, "archive": archive, "mctx": mctx, "tmp": tmp_path}


def test_pipeline_uses_ocr_when_pypdf_returns_no_text(setup):
    """When pypdf can't extract text but OCR can, the doc should classify normally."""
    pdf = synth_empty_pdf(setup["tmp"] / "scan.pdf")  # no embedded text
    fake = FakeClassifier(results=[_result()])

    # Patch ocr_text to return successfully — we're testing the pipeline wiring,
    # not Tesseract itself. (Tesseract is tested in test_pdf_ocr.py.)
    def fake_ocr(path, *, lang="deu+eng", max_chars=6 * 1024, dpi=200):
        return ("Rechnung Telekom 49,99 EUR", OcrStatus.OK)

    with patch("aido.worker.pipeline.ocr_text", side_effect=fake_ocr):
        pipe = Pipeline(
            conn=setup["conn"],
            classifier=fake,
            threshold=0.75,
            mutations=setup["mctx"],
            classifier_model="claude-opus-4-7",
            stabilize_seconds=0.0,
        )
        outcome = pipe.process(pdf)

    assert outcome is PipelineOutcome.AUTO_FILED
    from aido.pdf.hash import sha256_of_file  # noqa: E402
    # File has been moved to archive; we can't hash inbox path anymore
    moved = list(setup["archive"].rglob("*.pdf"))
    assert len(moved) == 1
    decision = find_by_source_hash(setup["conn"], sha256_of_file(moved[0]))
    assert decision is not None
    assert decision.status is DecisionStatus.AUTO_FILED
    assert fake.calls and fake.calls[0][0] == "Rechnung Telekom 49,99 EUR"


def test_pipeline_routes_to_review_when_ocr_also_empty(setup):
    """When both pypdf and OCR find no text, route to _review/."""
    pdf = synth_empty_pdf(setup["tmp"] / "blank.pdf")
    fake = FakeClassifier(results=[])  # classifier must not be called

    def fake_ocr(path, *, lang="deu+eng", max_chars=6 * 1024, dpi=200):
        return ("", OcrStatus.EMPTY)

    with patch("aido.worker.pipeline.ocr_text", side_effect=fake_ocr):
        pipe = Pipeline(
            conn=setup["conn"],
            classifier=fake,
            threshold=0.75,
            mutations=setup["mctx"],
            classifier_model="claude-opus-4-7",
            stabilize_seconds=0.0,
        )
        outcome = pipe.process(pdf)

    assert outcome is PipelineOutcome.REVIEW
    assert fake.calls == []
