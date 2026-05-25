import threading
from datetime import UTC, date, datetime

import pytest

from aido.daemon import HealthState
from aido.mutations import MutationContext
from aido.store.connection import connect
from aido.store.decisions import NewDecision, insert_decision
from aido.store.migrations import init_db
from aido.store.persons import create_person
from aido.store.taxonomy import create_category, create_doctype
from aido.types import DecisionStatus
from aido.webui.app import WebState, create_app


@pytest.fixture
def web(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    db = tmp_path / "x.sqlite"
    with connect(db) as conn:
        init_db(conn)
        timo = create_person(conn, slug="timo", display_name="Timo")
        cat = create_category(conn, slug="rechnungen", display_name="Rechnungen")
        create_category(conn, slug="_review", display_name="_review", is_review=True)
        dt = create_doctype(conn, slug="rechnung", display_name="Rechnung")
        filed = archive / "timo" / "rechnungen" / "2026-03-12_rechnung_telekom.pdf"
        filed.parent.mkdir(parents=True)
        filed.write_bytes(b"%PDF-1.4\n%pretend\n")
        new_id = insert_decision(
            conn,
            NewDecision(
                created_at=datetime(2026, 5, 17, 10, tzinfo=UTC),
                source_hash="h1",
                source_path="/s/x.pdf",
                filed_path=str(filed),
                person_id=timo.id,
                category_id=cat.id,
                doctype_id=dt.id,
                document_date=date(2026, 3, 12),
                counterparty="telekom",
                proposed_filename="2026-03-12_rechnung_telekom.pdf",
                overall_confidence=0.93,
                person_confidence=0.95,
                category_confidence=0.91,
                reasoning="recipient Timo; sender Telekom",
                classifier_model="claude-opus-4-7",
                new_category_proposal=None,
                needs_review=False,
                status=DecisionStatus.AUTO_FILED,
            ),
        )
    state = WebState(
        db_path=db,
        archive_root=archive,
        mutations=MutationContext(
            conn=None,  # webui doesn't reuse the worker's connection
            archive_root=archive,
            lock=threading.Lock(),
            now=lambda: datetime.now(UTC),
        ),
        health=HealthState(),
    )
    app = create_app(state)
    # nosemgrep: python.flask.security.audit.hardcoded-config.avoid_hardcoded_config_TESTING
    app.config["TESTING"] = True  # required by Flask's test client; this is a test fixture
    return app.test_client(), new_id, filed


def test_detail_renders(web):
    client, new_id, _ = web
    rv = client.get(f"/decisions/{new_id}")
    assert rv.status_code == 200
    body = rv.get_data(as_text=True)
    assert "telekom" in body.lower()
    assert "sender Telekom" in body  # reasoning shown
    assert f"/pdf/{new_id}" in body  # iframe src present


def test_detail_404_for_unknown(web):
    client, _, _ = web
    assert client.get("/decisions/9999").status_code == 404


def test_pdf_route_streams_bytes(web):
    client, new_id, _filed = web
    rv = client.get(f"/pdf/{new_id}")
    assert rv.status_code == 200
    assert rv.mimetype == "application/pdf"
    assert rv.data.startswith(b"%PDF-")


def test_pdf_route_404_when_file_missing(web):
    client, new_id, filed = web
    filed.unlink()
    assert client.get(f"/pdf/{new_id}").status_code == 404


def test_stats_renders(web):
    client, _, _ = web
    rv = client.get("/stats")
    assert rv.status_code == 200
    body = rv.get_data(as_text=True)
    assert "Stats" in body
    assert "needs_review" in body.lower() or "needs review" in body.lower()
