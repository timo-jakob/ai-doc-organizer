from datetime import UTC

import pytest

from aido.webui.app import WebState, create_app


@pytest.fixture
def web(tmp_path):
    import threading

    from aido.mutations import MutationContext
    from aido.store.connection import connect
    from aido.store.migrations import init_db
    from aido.store.persons import create_person
    from aido.store.taxonomy import create_category, create_doctype

    archive = tmp_path / "archive"
    archive.mkdir()
    db = tmp_path / "x.sqlite"
    with connect(db) as conn:
        init_db(conn)
        create_person(conn, slug="timo", display_name="Timo Jakob")
        create_category(conn, slug="rechnungen", display_name="Rechnungen")
        create_category(conn, slug="_review", display_name="_review", is_review=True)
        create_doctype(conn, slug="rechnung", display_name="Rechnung")
        from aido.daemon import HealthState

        state = WebState(
            db_path=db,
            archive_root=archive,
            mutations=MutationContext(
                conn=conn,
                archive_root=archive,
                lock=threading.Lock(),
                now=lambda: __import__("datetime").datetime.now(),
            ),
            health=HealthState(),
        )
        app = create_app(state)
        # nosemgrep: python.flask.security.audit.hardcoded-config.avoid_hardcoded_config_TESTING
        app.config["TESTING"] = True  # required by Flask's test client; this is a test fixture
        yield app.test_client()


def test_index_renders(web):
    rv = web.get("/")
    assert rv.status_code == 200
    # Base layout markers we'll add in Task 25.
    assert b"aido" in rv.data


def test_healthz_returns_json(web):
    rv = web.get("/healthz")
    assert rv.status_code == 200
    assert rv.is_json
    body = rv.get_json()
    assert body["status"] == "ok"
    assert "needs_review" in body


def test_needs_review_tab_shows_only_uncertain(web):
    # Drive through the daemon would be heavy; insert decisions directly.
    from datetime import datetime

    from aido.store.connection import connect
    from aido.store.decisions import NewDecision, insert_decision
    from aido.store.persons import get_person_by_slug
    from aido.store.taxonomy import get_category_by_slug, get_review_category
    from aido.types import DecisionStatus

    state = web.application.config["AIDO_STATE"]
    with connect(state.db_path) as conn:
        timo = get_person_by_slug(conn, "timo")
        cat = get_category_by_slug(conn, "rechnungen")
        review = get_review_category(conn)
        insert_decision(
            conn,
            NewDecision(
                created_at=datetime(2026, 5, 17, 10, tzinfo=UTC),
                source_hash="h1",
                source_path="/s",
                filed_path="/a",
                person_id=timo.id,
                category_id=cat.id,
                doctype_id=None,
                document_date=None,
                counterparty="t",
                proposed_filename="x.pdf",
                overall_confidence=0.9,
                person_confidence=0.9,
                category_confidence=0.9,
                reasoning="confident",
                classifier_model="m",
                new_category_proposal=None,
                needs_review=False,
                status=DecisionStatus.AUTO_FILED,
            ),
        )
        insert_decision(
            conn,
            NewDecision(
                created_at=datetime(2026, 5, 17, 11, tzinfo=UTC),
                source_hash="h2",
                source_path="/s",
                filed_path="/a",
                person_id=timo.id,
                category_id=review.id,
                doctype_id=None,
                document_date=None,
                counterparty=None,
                proposed_filename="uncertain.pdf",
                overall_confidence=0.4,
                person_confidence=0.4,
                category_confidence=0.4,
                reasoning="hesitant",
                classifier_model="m",
                new_category_proposal=None,
                needs_review=True,
                status=DecisionStatus.REVIEW,
            ),
        )

    rv_all = web.get("/all")
    assert rv_all.status_code == 200
    body = rv_all.get_data(as_text=True)
    assert "x.pdf" in body
    assert "uncertain.pdf" in body

    rv_review = web.get("/needs-review")
    body = rv_review.get_data(as_text=True)
    assert "uncertain.pdf" in body
    assert "x.pdf" not in body
