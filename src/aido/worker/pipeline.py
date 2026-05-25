"""End-to-end processing of a single PDF.

Catches every exception. Never raises out of `process()`. Returns a
`PipelineOutcome` describing what happened, so callers can log it.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from aido.classifier.base import Classifier
from aido.classifier.routing import RouteDecision, route
from aido.filing.executor import FilingTarget, file_document
from aido.mutations import MutationContext
from aido.pdf.extract import ExtractStatus, extract_text
from aido.pdf.hash import sha256_of_file
from aido.pdf.ocr import OcrStatus, ocr_text
from aido.store.decisions import NewDecision, find_by_source_hash, insert_decision
from aido.store.persons import get_person_by_slug
from aido.store.taxonomy import get_review_category
from aido.types import (
    ClassificationResult,
    DecisionStatus,
    RouteOutcome,
)

_log = logging.getLogger("aido.pipeline")


class PipelineOutcome(StrEnum):
    AUTO_FILED = "auto_filed"
    REVIEW = "review"
    DUPLICATE_SKIP = "duplicate_skip"
    FAILED = "failed"


class Pipeline:
    def __init__(
        self,
        *,
        conn: sqlite3.Connection,
        classifier: Classifier,
        threshold: float,
        mutations: MutationContext,
        classifier_model: str,
        stabilize_seconds: float = 2.0,
    ) -> None:
        self._conn = conn
        self._classifier = classifier
        self._threshold = threshold
        self._mutations = mutations
        self._model = classifier_model
        self._stabilize = stabilize_seconds

    def process(self, src: Path) -> PipelineOutcome:
        try:
            return self._process(src)
        except Exception:
            _log.exception("pipeline.crashed", extra={"source_path": str(src)})
            return PipelineOutcome.FAILED

    def _process(self, src: Path) -> PipelineOutcome:
        self._wait_until_stable(src)
        if not src.exists():
            _log.warning("pipeline.source_missing", extra={"source_path": str(src)})
            return PipelineOutcome.FAILED

        source_hash = sha256_of_file(src)
        if find_by_source_hash(self._conn, source_hash) is not None:
            _log.info(
                "pipeline.duplicate_skip",
                extra={"source_path": str(src), "source_hash": source_hash},
            )
            src.unlink(missing_ok=True)
            return PipelineOutcome.DUPLICATE_SKIP

        text, status = extract_text(src)
        if status is ExtractStatus.NO_TEXT:
            ocr_t, ocr_status = ocr_text(src)
            if ocr_status is OcrStatus.OK:
                text = ocr_t
                status = ExtractStatus.OK
                _log.info(
                    "pipeline.ocr_fallback_used",
                    extra={"source_path": str(src), "chars": len(text)},
                )
        if status is not ExtractStatus.OK:
            return self._route_to_review_no_classify(
                src,
                source_hash=source_hash,
                reason=status.value,
            )

        try:
            result = self._classifier.classify(text=text, original_filename=src.name)
        except Exception as exc:
            _log.exception(
                "pipeline.classifier_failed",
                extra={"source_hash": source_hash, "error": str(exc)},
            )
            return self._route_to_review_no_classify(
                src,
                source_hash=source_hash,
                reason=f"classifier_error: {exc}",
            )

        decision = route(self._conn, result, threshold=self._threshold)
        target = self._build_target(decision, result)
        dest = file_document(src, archive_root=self._mutations.archive_root, target=target)

        new_id = self._record_decision(
            source_hash=source_hash,
            source_path=src,
            filed_path=dest,
            result=result,
            decision=decision,
        )
        _log.info(
            "pipeline.filed",
            extra={
                "decision_id": new_id,
                "source_hash": source_hash,
                "outcome": decision.outcome.value,
                "filed_path": str(dest),
                "model": self._model,
            },
        )
        return (
            PipelineOutcome.AUTO_FILED
            if decision.outcome is RouteOutcome.AUTO_FILE
            else PipelineOutcome.REVIEW
        )

    # ------------------------------------------------------------------
    # Helpers

    def _wait_until_stable(self, path: Path) -> None:
        if self._stabilize <= 0:
            return
        try:
            last_size = -1
            while True:
                size = path.stat().st_size
                if size == last_size:
                    return
                last_size = size
                time.sleep(self._stabilize)
        except FileNotFoundError:
            return

    def _build_target(self, decision: RouteDecision, result: ClassificationResult) -> FilingTarget:
        if decision.outcome is RouteOutcome.AUTO_FILE:
            assert decision.person_id is not None
            assert decision.category_id is not None
            person_slug = self._slug_of_person(decision.person_id)
            cat_slug = self._slug_of_category(decision.category_id)
            return FilingTarget(
                person_slug=person_slug,
                category_slug=cat_slug,
                filename=result.proposed_filename,
            )
        # REVIEW path → top-level _review/
        review_cat = get_review_category(self._conn)
        assert review_cat is not None
        return FilingTarget(
            person_slug=None,
            category_slug=review_cat.slug,
            filename=result.proposed_filename,
        )

    def _route_to_review_no_classify(
        self, src: Path, *, source_hash: str, reason: str
    ) -> PipelineOutcome:
        """Path used when text extraction or classification fails BEFORE we
        have a ClassificationResult. We still record a decision row pointing
        to the file in _review/.
        """
        review_cat = get_review_category(self._conn)
        assert review_cat is not None, "DB missing _review category"
        filename = f"{datetime.now(UTC).date().isoformat()}_uncertain_{source_hash[:8]}.pdf"
        dest = file_document(
            src,
            archive_root=self._mutations.archive_root,
            target=FilingTarget(person_slug=None, category_slug=review_cat.slug, filename=filename),
        )
        # Need a person_id to satisfy FK; use 'shared' if it exists, else any active person.
        person = get_person_by_slug(self._conn, "shared") or self._any_person()
        if person is None:
            _log.error(
                "pipeline.no_person_for_review",
                extra={"source_hash": source_hash, "reason": reason},
            )
            return PipelineOutcome.FAILED
        with self._conn:
            insert_decision(
                self._conn,
                NewDecision(
                    created_at=self._mutations.now(),
                    source_hash=source_hash,
                    source_path=str(src),
                    filed_path=str(dest),
                    person_id=person.id,
                    category_id=review_cat.id,
                    doctype_id=None,
                    document_date=None,
                    counterparty=None,
                    proposed_filename=filename,
                    overall_confidence=0.0,
                    person_confidence=0.0,
                    category_confidence=0.0,
                    reasoning=reason,
                    classifier_model=self._model,
                    new_category_proposal=None,
                    needs_review=True,
                    status=DecisionStatus.REVIEW,
                ),
            )
        return PipelineOutcome.REVIEW

    def _record_decision(
        self,
        *,
        source_hash: str,
        source_path: Path,
        filed_path: Path,
        result: ClassificationResult,
        decision: RouteDecision,
    ) -> int:
        needs_review = decision.outcome is RouteOutcome.REVIEW
        status = (
            DecisionStatus.AUTO_FILED
            if decision.outcome is RouteOutcome.AUTO_FILE
            else DecisionStatus.REVIEW
        )
        reasoning = result.reasoning
        if decision.reason is not None:
            reasoning = f"[{decision.reason.value}] {reasoning}"
        # If person/category id couldn't be resolved (unknown_person etc.),
        # we need to satisfy FK with something — use a fallback person.
        person_id = decision.person_id
        if person_id is None:
            person = get_person_by_slug(self._conn, "shared") or self._any_person()
            assert person is not None, "DB has no persons; run 'aido init'"
            person_id = person.id
        category_id = decision.category_id
        assert category_id is not None  # routing always returns at least _review.id
        with self._conn:
            return insert_decision(
                self._conn,
                NewDecision(
                    created_at=self._mutations.now(),
                    source_hash=source_hash,
                    source_path=str(source_path),
                    filed_path=str(filed_path),
                    person_id=person_id,
                    category_id=category_id,
                    doctype_id=decision.doctype_id,
                    document_date=result.document_date,
                    counterparty=result.counterparty or None,
                    proposed_filename=result.proposed_filename,
                    overall_confidence=result.overall_confidence,
                    person_confidence=result.person_confidence,
                    category_confidence=result.category_confidence,
                    reasoning=reasoning,
                    classifier_model=self._model,
                    new_category_proposal=result.new_category_proposal,
                    needs_review=needs_review,
                    status=status,
                ),
            )

    def _slug_of_person(self, person_id: int) -> str:
        row = self._conn.execute("SELECT slug FROM persons WHERE id = ?", (person_id,)).fetchone()
        assert row is not None
        return row["slug"]

    def _slug_of_category(self, category_id: int) -> str:
        row = self._conn.execute(
            "SELECT slug FROM categories WHERE id = ?", (category_id,)
        ).fetchone()
        assert row is not None
        return row["slug"]

    def _any_person(self):
        from aido.store.persons import list_persons

        persons = list_persons(self._conn)
        return persons[0] if persons else None
