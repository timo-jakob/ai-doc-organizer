"""Domain types and enums for aido."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class DecisionStatus(StrEnum):
    AUTO_FILED = "auto_filed"
    REVIEW = "review"
    HUMAN_FILED = "human_filed"
    FAILED = "failed"


class ManualAction(StrEnum):
    RE_FILE = "re_file"
    RENAME = "rename"
    DELETE = "delete"
    APPROVE = "approve"
    PROMOTE_CATEGORY = "promote_category"


class RouteOutcome(StrEnum):
    AUTO_FILE = "auto_file"
    REVIEW = "review"


def _check_confidence(name: str, value: float) -> None:
    if not (0.0 <= value <= 1.0):
        raise ValueError(f"{name} must be in [0, 1], got {value!r}")


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    """Output of a Classifier.classify() call.

    The classifier returns slugs, not IDs. Slug → ID resolution is done by
    aido.classifier.routing (see Task 12).
    """

    person_slug: str
    category_slug: str
    doctype_slug: str
    document_date: date
    counterparty: str
    proposed_filename: str
    overall_confidence: float
    person_confidence: float
    category_confidence: float
    new_category_proposal: str | None
    reasoning: str

    def __post_init__(self) -> None:
        _check_confidence("overall_confidence", self.overall_confidence)
        _check_confidence("person_confidence", self.person_confidence)
        _check_confidence("category_confidence", self.category_confidence)
