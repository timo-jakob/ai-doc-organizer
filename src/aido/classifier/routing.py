"""Slug resolution + auto-file/review decision."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import StrEnum

from aido.store.persons import get_person_by_slug
from aido.store.taxonomy import (
    get_category_by_slug,
    get_doctype_by_slug,
    get_review_category,
)
from aido.types import ClassificationResult, RouteOutcome

_DOCTYPE_FALLBACK_SLUG = "letter"


class RouteReason(StrEnum):
    LOW_CONFIDENCE = "low_confidence"
    NEW_CATEGORY_PROPOSAL = "new_category_proposal"
    UNKNOWN_PERSON = "unknown_person"
    UNKNOWN_CATEGORY = "unknown_category"


@dataclass(frozen=True, slots=True)
class RouteDecision:
    outcome: RouteOutcome
    person_id: int | None
    category_id: int | None  # _review category id when outcome=REVIEW and reason is known
    doctype_id: int | None
    reason: RouteReason | None  # None on AUTO_FILE


def route(
    conn: sqlite3.Connection,
    result: ClassificationResult,
    *,
    threshold: float,
) -> RouteDecision:
    """Resolve slugs to IDs and decide auto-file vs. review."""
    review_cat = get_review_category(conn)
    if review_cat is None:
        raise RuntimeError(
            "No _review category in the database; run 'aido init' before classifying."
        )

    person = get_person_by_slug(conn, result.person_slug)
    if person is None:
        return RouteDecision(
            outcome=RouteOutcome.REVIEW,
            person_id=None,
            category_id=review_cat.id,
            doctype_id=None,
            reason=RouteReason.UNKNOWN_PERSON,
        )

    category = get_category_by_slug(conn, result.category_slug)
    if category is None:
        return RouteDecision(
            outcome=RouteOutcome.REVIEW,
            person_id=person.id,
            category_id=review_cat.id,
            doctype_id=None,
            reason=RouteReason.UNKNOWN_CATEGORY,
        )

    doctype = get_doctype_by_slug(conn, result.doctype_slug)
    if doctype is None:
        # Fall back to the 'letter' generic doctype if available; else None.
        fallback = get_doctype_by_slug(conn, _DOCTYPE_FALLBACK_SLUG)
        doctype_id = fallback.id if fallback else None
    else:
        doctype_id = doctype.id

    if result.new_category_proposal:
        return RouteDecision(
            outcome=RouteOutcome.REVIEW,
            person_id=person.id,
            category_id=review_cat.id,
            doctype_id=doctype_id,
            reason=RouteReason.NEW_CATEGORY_PROPOSAL,
        )

    if result.overall_confidence < threshold:
        return RouteDecision(
            outcome=RouteOutcome.REVIEW,
            person_id=person.id,
            category_id=review_cat.id,
            doctype_id=doctype_id,
            reason=RouteReason.LOW_CONFIDENCE,
        )

    return RouteDecision(
        outcome=RouteOutcome.AUTO_FILE,
        person_id=person.id,
        category_id=category.id,
        doctype_id=doctype_id,
        reason=None,
    )
