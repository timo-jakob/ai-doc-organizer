from datetime import UTC, datetime, timedelta

import pytest

from aido.store.connection import connect
from aido.store.manual_actions import (
    NewManualAction,
    insert_manual_action,
    list_actions_for_decision,
)
from aido.store.migrations import init_db
from aido.store.pending_jobs import (
    claim_due,
    delete_pending,
    enqueue_pending,
    record_attempt,
)
from aido.store.persons import create_person
from aido.store.taxonomy import create_category
from aido.types import ManualAction


@pytest.fixture
def conn(tmp_path):
    with connect(tmp_path / "x.sqlite") as c:
        init_db(c)
        yield c


def test_insert_and_list_manual_action(conn):
    p = create_person(conn, slug="timo", display_name="Timo")
    cat = create_category(conn, slug="x", display_name="X")
    # We need a decision id to FK to; minimal insert via raw SQL is fine.
    cur = conn.execute(
        "INSERT INTO decisions("
        "  created_at, source_hash, source_path, filed_path, person_id, category_id, "
        "  proposed_filename, overall_confidence, person_confidence, category_confidence, "
        "  classifier_model, needs_review, status"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "2026-05-17T10:00:00",
            "h",
            "/s",
            "/d",
            p.id,
            cat.id,
            "x.pdf",
            0.9,
            0.9,
            0.9,
            "claude-opus-4-7",
            0,
            "auto_filed",
        ),
    )
    decision_id = cur.lastrowid

    new_id = insert_manual_action(
        conn,
        NewManualAction(
            decision_id=decision_id,
            action=ManualAction.RE_FILE,
            before_path="/d",
            after_path="/d2",
            before_person_id=p.id,
            after_person_id=p.id,
            before_category_id=cat.id,
            after_category_id=cat.id,
            created_at=datetime(2026, 5, 17, 10, 5, tzinfo=UTC),
            note=None,
        ),
    )
    rows = list_actions_for_decision(conn, decision_id)
    assert len(rows) == 1
    assert rows[0].id == new_id
    assert rows[0].action == ManualAction.RE_FILE


def test_enqueue_and_claim_due(conn):
    now = datetime(2026, 5, 17, 10, 0, tzinfo=UTC)
    enqueue_pending(
        conn,
        source_path="/s/a.pdf",
        source_hash="h1",
        next_attempt_at=now - timedelta(seconds=1),
        created_at=now,
    )
    enqueue_pending(
        conn,
        source_path="/s/b.pdf",
        source_hash="h2",
        next_attempt_at=now + timedelta(minutes=10),
        created_at=now,
    )
    due = claim_due(conn, now=now, limit=10)
    hashes = [j.source_hash for j in due]
    assert hashes == ["h1"]


def test_record_attempt_increments_and_pushes_next_time(conn):
    now = datetime(2026, 5, 17, 10, 0, tzinfo=UTC)
    enqueue_pending(
        conn, source_path="/s/a.pdf", source_hash="h1", next_attempt_at=now, created_at=now
    )
    [job] = claim_due(conn, now=now, limit=10)
    record_attempt(conn, job.id, error="boom", next_attempt_at=now + timedelta(seconds=30))
    [updated] = claim_due(conn, now=now + timedelta(minutes=1), limit=10)
    assert updated.attempts == 1
    assert updated.last_error == "boom"


def test_delete_pending(conn):
    now = datetime(2026, 5, 17, 10, 0, tzinfo=UTC)
    enqueue_pending(
        conn, source_path="/s/a.pdf", source_hash="h1", next_attempt_at=now, created_at=now
    )
    [job] = claim_due(conn, now=now, limit=10)
    delete_pending(conn, job.id)
    assert claim_due(conn, now=now, limit=10) == []


def test_enqueue_duplicate_hash_raises(conn):
    now = datetime(2026, 5, 17, 10, 0, tzinfo=UTC)
    enqueue_pending(
        conn, source_path="/s/a.pdf", source_hash="h1", next_attempt_at=now, created_at=now
    )
    with pytest.raises(Exception):
        enqueue_pending(
            conn, source_path="/s/a.pdf", source_hash="h1", next_attempt_at=now, created_at=now
        )
