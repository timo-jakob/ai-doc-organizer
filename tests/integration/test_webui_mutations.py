import threading
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from aido.daemon import HealthState
from aido.mutations import MutationContext
from aido.store.connection import connect
from aido.store.decisions import (
    NewDecision,
    get_decision,
    insert_decision,
)
from aido.store.manual_actions import list_actions_for_decision
from aido.store.migrations import init_db
from aido.store.persons import create_person
from aido.store.taxonomy import create_category, create_doctype, get_category_by_slug
from aido.types import DecisionStatus, ManualAction
from aido.webui.app import WebState, create_app


@pytest.fixture
def web(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    db = tmp_path / "x.sqlite"
    with connect(db) as conn:
        init_db(conn)
        timo = create_person(conn, slug="timo", display_name="Timo")
        anna = create_person(conn, slug="anna", display_name="Anna")
        cat = create_category(conn, slug="rechnungen", display_name="Rechnungen")
        create_category(conn, slug="steuer", display_name="Steuer")
        create_category(conn, slug="_review", display_name="_review", is_review=True)
        dt = create_doctype(conn, slug="rechnung", display_name="Rechnung")
        filed = archive / "timo" / "rechnungen" / "x.pdf"
        filed.parent.mkdir(parents=True)
        filed.write_bytes(b"%PDF-1.4")
        new_id = insert_decision(conn, NewDecision(
            created_at=datetime(2026, 5, 17, 10, tzinfo=timezone.utc),
            source_hash="h1", source_path="/s/x.pdf", filed_path=str(filed),
            person_id=timo.id, category_id=cat.id, doctype_id=dt.id,
            document_date=date(2026, 3, 12), counterparty="telekom",
            proposed_filename="x.pdf",
            overall_confidence=0.93, person_confidence=0.95, category_confidence=0.91,
            reasoning="r", classifier_model="m",
            new_category_proposal=None, needs_review=False,
            status=DecisionStatus.AUTO_FILED,
        ))
    # Connection used by WebState — keep open for the duration of the test.
    state_conn_ctx = connect(db)
    conn = state_conn_ctx.__enter__()
    state = WebState(
        db_path=db,
        archive_root=archive,
        mutations=MutationContext(
            conn=conn,
            archive_root=archive,
            lock=threading.Lock(),
            now=lambda: datetime(2026, 5, 17, 12, tzinfo=timezone.utc),
        ),
        health=HealthState(),
    )
    app = create_app(state)
    app.config["TESTING"] = True
    yield app.test_client(), new_id
    state_conn_ctx.__exit__(None, None, None)


def test_post_refile_moves_and_audits(web):
    client, decision_id = web
    rv = client.post(f"/decisions/{decision_id}/re-file", json={
        "person_slug": "anna",
        "category_slug": "steuer",
        "filename": "moved.pdf",
    })
    assert rv.status_code == 200
    assert rv.get_json() == {"ok": True}
    state = client.application.config["AIDO_STATE"]
    d = get_decision(state.mutations.conn, decision_id)
    assert "anna" in d.filed_path and "steuer" in d.filed_path
    [audit] = list_actions_for_decision(state.mutations.conn, decision_id)
    assert audit.action == ManualAction.RE_FILE


def test_post_approve(web):
    client, decision_id = web
    state = client.application.config["AIDO_STATE"]
    state.mutations.conn.execute(
        "UPDATE decisions SET needs_review = 1 WHERE id = ?", (decision_id,)
    )
    rv = client.post(f"/decisions/{decision_id}/approve", json={})
    assert rv.status_code == 200
    d = get_decision(state.mutations.conn, decision_id)
    assert d.needs_review is False


def test_post_delete(web):
    client, decision_id = web
    rv = client.post(f"/decisions/{decision_id}/delete", json={})
    assert rv.status_code == 200


def test_post_promote_category_creates_and_refiles(web):
    client, decision_id = web
    state = client.application.config["AIDO_STATE"]
    rv = client.post(f"/decisions/{decision_id}/promote-category", json={
        "new_category_slug": "garten",
        "new_category_display_name": "Garten",
        "person_slug": "timo",
        "filename": "garten_doc.pdf",
    })
    assert rv.status_code == 200
    assert get_category_by_slug(state.mutations.conn, "garten") is not None


def test_unknown_decision_returns_404(web):
    client, _ = web
    rv = client.post("/decisions/9999/re-file", json={
        "person_slug": "anna", "category_slug": "steuer", "filename": "x.pdf",
    })
    assert rv.status_code == 404
