import threading
from datetime import UTC, datetime

import pytest

from aido.daemon import HealthState
from aido.mutations import MutationContext
from aido.store.connection import connect
from aido.store.migrations import init_db
from aido.store.persons import (
    create_person,
    find_person_by_alias,
    get_person_by_slug,
    list_aliases_for,
)
from aido.store.taxonomy import create_category, get_category_by_slug, get_doctype_by_slug
from aido.webui.app import WebState, create_app


@pytest.fixture
def web(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    db = tmp_path / "x.sqlite"
    with connect(db) as conn:
        init_db(conn)
        create_person(conn, slug="timo", display_name="Timo")
        create_category(conn, slug="_review", display_name="_review", is_review=True)
    state_conn_ctx = connect(db)
    conn = state_conn_ctx.__enter__()
    state = WebState(
        db_path=db,
        archive_root=archive,
        mutations=MutationContext(
            conn=conn,
            archive_root=archive,
            lock=threading.Lock(),
            now=lambda: datetime.now(UTC),
        ),
        health=HealthState(),
    )
    app = create_app(state)
    # nosemgrep: python.flask.security.audit.hardcoded-config.avoid_hardcoded_config_TESTING
    app.config["TESTING"] = True  # required by Flask's test client; this is a test fixture
    yield app.test_client(), conn
    state_conn_ctx.__exit__(None, None, None)


def test_settings_renders(web):
    client, _ = web
    rv = client.get("/settings")
    assert rv.status_code == 200
    body = rv.get_data(as_text=True)
    assert "timo" in body
    assert "Persons" in body
    assert "Categories" in body
    assert "Doctypes" in body


def test_add_person(web):
    client, conn = web
    rv = client.post(
        "/settings/persons",
        json={
            "slug": "anna",
            "display_name": "Anna Jakob",
            "is_shared": False,
            "aliases": ["Anna Jakob"],
        },
    )
    assert rv.status_code == 200
    assert get_person_by_slug(conn, "anna") is not None
    p = get_person_by_slug(conn, "anna")
    assert [a.alias for a in list_aliases_for(conn, p.id)] == ["Anna Jakob"]


def test_add_alias_to_existing(web):
    client, conn = web
    timo = get_person_by_slug(conn, "timo")
    rv = client.post(f"/settings/persons/{timo.id}/aliases", json={"alias": "Jakob"})
    assert rv.status_code == 200
    assert find_person_by_alias(conn, "jakob").id == timo.id


def test_add_category(web):
    client, conn = web
    rv = client.post(
        "/settings/categories",
        json={
            "slug": "garten",
            "display_name": "Garten",
            "description": "Garten-Sachen",
        },
    )
    assert rv.status_code == 200
    assert get_category_by_slug(conn, "garten") is not None


def test_add_doctype(web):
    client, conn = web
    rv = client.post(
        "/settings/doctypes",
        json={
            "slug": "gartenrechnung",
            "display_name": "Gartenrechnung",
        },
    )
    assert rv.status_code == 200
    assert get_doctype_by_slug(conn, "gartenrechnung") is not None


def test_duplicate_slug_returns_400(web):
    client, _ = web
    client.post("/settings/categories", json={"slug": "garten", "display_name": "G"})
    rv = client.post("/settings/categories", json={"slug": "garten", "display_name": "G2"})
    assert rv.status_code == 400
