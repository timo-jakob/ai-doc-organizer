from datetime import date

import pytest

from aido.types import (
    ClassificationResult,
    DecisionStatus,
    ManualAction,
    RouteOutcome,
)


def test_decision_status_values():
    assert DecisionStatus.AUTO_FILED.value == "auto_filed"
    assert DecisionStatus.REVIEW.value == "review"
    assert DecisionStatus.HUMAN_FILED.value == "human_filed"
    assert DecisionStatus.FAILED.value == "failed"


def test_manual_action_values():
    assert ManualAction.RE_FILE.value == "re_file"
    assert ManualAction.RENAME.value == "rename"
    assert ManualAction.DELETE.value == "delete"
    assert ManualAction.APPROVE.value == "approve"
    assert ManualAction.PROMOTE_CATEGORY.value == "promote_category"


def test_decision_status_is_str_enum():
    assert isinstance(DecisionStatus.AUTO_FILED, str)
    assert DecisionStatus.AUTO_FILED == "auto_filed"


def test_classification_result_constructs():
    r = ClassificationResult(
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
        reasoning="Recipient 'Timo Jakob'; sender Telekom; invoice format.",
    )
    assert r.person_slug == "timo"
    assert r.document_date == date(2026, 3, 12)
    assert r.new_category_proposal is None


def test_classification_result_rejects_invalid_confidence():
    with pytest.raises(ValueError):
        ClassificationResult(
            person_slug="timo",
            category_slug="rechnungen",
            doctype_slug="rechnung",
            document_date=date(2026, 3, 12),
            counterparty="telekom",
            proposed_filename="x.pdf",
            overall_confidence=1.5,  # invalid
            person_confidence=0.9,
            category_confidence=0.9,
            new_category_proposal=None,
            reasoning="",
        )


def test_route_outcome_enum():
    assert RouteOutcome.AUTO_FILE.value == "auto_file"
    assert RouteOutcome.REVIEW.value == "review"
