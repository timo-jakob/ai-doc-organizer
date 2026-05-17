from datetime import date

import pytest

from aido.classifier.routing import RouteDecision, RouteReason, route
from aido.store.connection import connect
from aido.store.migrations import init_db
from aido.store.persons import create_person
from aido.store.taxonomy import create_category, create_doctype
from aido.types import ClassificationResult, RouteOutcome


@pytest.fixture
def conn(tmp_path):
    with connect(tmp_path / "x.sqlite") as c:
        init_db(c)
        create_person(c, slug="timo", display_name="Timo")
        create_person(c, slug="shared", display_name="Shared", is_shared=True)
        create_category(c, slug="rechnungen", display_name="Rechnungen")
        create_category(c, slug="_review", display_name="_review", is_review=True)
        create_doctype(c, slug="rechnung", display_name="Rechnung")
        create_doctype(c, slug="letter", display_name="Letter")
        yield c


def _r(**over):
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
        reasoning="x",
    )
    base.update(over)
    return ClassificationResult(**base)


def test_high_confidence_auto_files(conn):
    decision = route(conn, _r(), threshold=0.75)
    assert decision.outcome == RouteOutcome.AUTO_FILE
    assert decision.person_id is not None
    assert decision.category_id is not None
    assert decision.doctype_id is not None
    assert decision.reason is None


def test_low_confidence_routes_to_review(conn):
    decision = route(conn, _r(overall_confidence=0.5), threshold=0.75)
    assert decision.outcome == RouteOutcome.REVIEW
    assert decision.reason == RouteReason.LOW_CONFIDENCE
    # Category is _review on review path.
    review_cat = decision.category_id
    assert review_cat is not None


def test_new_category_proposal_routes_to_review(conn):
    decision = route(
        conn,
        _r(new_category_proposal="garten", category_slug="rechnungen"),
        threshold=0.75,
    )
    assert decision.outcome == RouteOutcome.REVIEW
    assert decision.reason == RouteReason.NEW_CATEGORY_PROPOSAL


def test_unknown_person_slug_routes_to_review(conn):
    decision = route(conn, _r(person_slug="ghost"), threshold=0.75)
    assert decision.outcome == RouteOutcome.REVIEW
    assert decision.reason == RouteReason.UNKNOWN_PERSON


def test_unknown_category_slug_routes_to_review(conn):
    decision = route(conn, _r(category_slug="nope"), threshold=0.75)
    assert decision.outcome == RouteOutcome.REVIEW
    assert decision.reason == RouteReason.UNKNOWN_CATEGORY


def test_unknown_doctype_falls_back_to_letter(conn):
    # 'letter' exists from the fixture, so unknown doctype resolves to it.
    decision = route(conn, _r(doctype_slug="totally-unknown"), threshold=0.75)
    assert decision.outcome == RouteOutcome.AUTO_FILE
    # doctype_id resolved to the 'letter' fallback.
    assert decision.doctype_id is not None


def test_missing_review_category_raises(tmp_path):
    """If the DB has no _review row, routing is broken; surface loudly."""
    with connect(tmp_path / "y.sqlite") as c:
        init_db(c)
        create_person(c, slug="timo", display_name="Timo")
        create_category(c, slug="rechnungen", display_name="Rechnungen")
        with pytest.raises(RuntimeError, match="_review"):
            route(c, _r(overall_confidence=0.1), threshold=0.75)
