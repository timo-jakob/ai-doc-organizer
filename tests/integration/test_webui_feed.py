from datetime import date

import pytest

from aido.webui.app import create_app, WebState


@pytest.fixture
def web(tmp_path):
    from aido.store.connection import connect
    from aido.store.migrations import init_db
    from aido.store.persons import create_person
    from aido.store.taxonomy import create_category, create_doctype
    import threading
    from aido.mutations import MutationContext
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
                conn=conn, archive_root=archive, lock=threading.Lock(),
                now=lambda: __import__("datetime").datetime.now(),
            ),
            health=HealthState(),
        )
        app = create_app(state)
        app.config["TESTING"] = True
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
