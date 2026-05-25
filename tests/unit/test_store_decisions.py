import sqlite3
from datetime import UTC, date, datetime

import pytest

from aido.store.connection import connect
from aido.store.decisions import (
    DecisionRow,
    DecisionUpdate,
    NewDecision,
    count_needs_review,
    find_by_source_hash,
    get_decision,
    insert_decision,
    list_recent,
    update_decision,
)
from aido.store.migrations import init_db
from aido.store.persons import create_person
from aido.store.taxonomy import create_category, create_doctype
from aido.types import DecisionStatus


@pytest.fixture
def ctx(tmp_path):
    with connect(tmp_path / "x.sqlite") as c:
        init_db(c)
        p = create_person(c, slug="timo", display_name="Timo Jakob")
        cat = create_category(c, slug="rechnungen", display_name="Rechnungen")
        dt = create_doctype(c, slug="rechnung", display_name="Rechnung")
        review = create_category(c, slug="_review", display_name="_review", is_review=True)
        yield c, p, cat, dt, review


def _sample(p_id: int, c_id: int, d_id: int | None, *, source_hash: str = "h1") -> NewDecision:
    return NewDecision(
        created_at=datetime(2026, 5, 17, 10, 0, tzinfo=UTC),
        source_hash=source_hash,
        source_path="/scans/scan001.pdf",
        filed_path="/archive/timo/rechnungen/2026-03-12_rechnung_telekom.pdf",
        person_id=p_id,
        category_id=c_id,
        doctype_id=d_id,
        document_date=date(2026, 3, 12),
        counterparty="telekom",
        proposed_filename="2026-03-12_rechnung_telekom.pdf",
        overall_confidence=0.93,
        person_confidence=0.95,
        category_confidence=0.91,
        reasoning="recipient Timo Jakob; sender Telekom",
        classifier_model="claude-opus-4-7",
        new_category_proposal=None,
        needs_review=False,
        status=DecisionStatus.AUTO_FILED,
    )


def test_insert_and_get(ctx):
    conn, p, cat, dt, _ = ctx
    new_id = insert_decision(conn, _sample(p.id, cat.id, dt.id))
    got = get_decision(conn, new_id)
    assert isinstance(got, DecisionRow)
    assert got.id == new_id
    assert got.source_hash == "h1"
    assert got.status == DecisionStatus.AUTO_FILED
    assert got.document_date == date(2026, 3, 12)
    assert got.needs_review is False


def test_insert_duplicate_source_hash_raises(ctx):
    conn, p, cat, dt, _ = ctx
    insert_decision(conn, _sample(p.id, cat.id, dt.id))
    with pytest.raises(sqlite3.IntegrityError):
        insert_decision(conn, _sample(p.id, cat.id, dt.id, source_hash="h1"))


def test_find_by_source_hash(ctx):
    conn, p, cat, dt, _ = ctx
    new_id = insert_decision(conn, _sample(p.id, cat.id, dt.id))
    assert find_by_source_hash(conn, "h1").id == new_id
    assert find_by_source_hash(conn, "nope") is None


def test_list_recent_orders_descending(ctx):
    conn, p, cat, dt, _ = ctx
    a = _sample(p.id, cat.id, dt.id, source_hash="a")
    b = _sample(p.id, cat.id, dt.id, source_hash="b")
    b = NewDecision(**{**b.__dict__, "created_at": datetime(2026, 5, 17, 11, 0, tzinfo=UTC)})
    insert_decision(conn, a)
    insert_decision(conn, b)
    rows = list_recent(conn, limit=10)
    assert [r.source_hash for r in rows] == ["b", "a"]


def test_count_needs_review(ctx):
    conn, p, cat, dt, review = ctx
    insert_decision(conn, _sample(p.id, cat.id, dt.id, source_hash="a"))
    rv = _sample(p.id, review.id, None, source_hash="b")
    rv = NewDecision(**{**rv.__dict__, "needs_review": True, "status": DecisionStatus.REVIEW})
    insert_decision(conn, rv)
    assert count_needs_review(conn) == 1


def test_update_decision_changes_path_and_category(ctx):
    conn, p, cat, dt, _ = ctx
    other_cat = create_category(conn, slug="steuer", display_name="Steuer")
    new_id = insert_decision(conn, _sample(p.id, cat.id, dt.id))
    update_decision(
        conn,
        new_id,
        DecisionUpdate(
            filed_path="/archive/timo/steuer/x.pdf",
            category_id=other_cat.id,
            status=DecisionStatus.HUMAN_FILED,
            needs_review=False,
        ),
    )
    got = get_decision(conn, new_id)
    assert got.filed_path == "/archive/timo/steuer/x.pdf"
    assert got.category_id == other_cat.id
    assert got.status == DecisionStatus.HUMAN_FILED
