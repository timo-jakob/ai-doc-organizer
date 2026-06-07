import threading
from datetime import UTC, date, datetime
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
        _ = create_person(conn, slug="anna", display_name="Anna")
        cat = create_category(conn, slug="rechnungen", display_name="Rechnungen")
        create_category(conn, slug="steuer", display_name="Steuer")
        create_category(conn, slug="_review", display_name="_review", is_review=True)
        dt = create_doctype(conn, slug="rechnung", display_name="Rechnung")
        filed = archive / "timo" / "rechnungen" / "x.pdf"
        filed.parent.mkdir(parents=True)
        filed.write_bytes(b"%PDF-1.4")
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
                proposed_filename="x.pdf",
                overall_confidence=0.93,
                person_confidence=0.95,
                category_confidence=0.91,
                reasoning="r",
                classifier_model="m",
                new_category_proposal=None,
                needs_review=False,
                status=DecisionStatus.AUTO_FILED,
            ),
        )
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
            now=lambda: datetime(2026, 5, 17, 12, tzinfo=UTC),
        ),
        health=HealthState(),
    )
    app = create_app(state)
    # nosemgrep: python.flask.security.audit.hardcoded-config.avoid_hardcoded_config_TESTING
    app.config["TESTING"] = True  # required by Flask's test client; this is a test fixture
    yield app.test_client(), new_id
    state_conn_ctx.__exit__(None, None, None)


def test_post_refile_moves_and_audits(web):
    client, decision_id = web
    rv = client.post(
        f"/decisions/{decision_id}/re-file",
        json={
            "person_slug": "anna",
            "category_slug": "steuer",
            "filename": "moved.pdf",
        },
    )
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
    rv = client.post(
        f"/decisions/{decision_id}/promote-category",
        json={
            "new_category_slug": "garten",
            "new_category_display_name": "Garten",
            "person_slug": "timo",
            "filename": "garten_doc.pdf",
        },
    )
    assert rv.status_code == 200
    assert get_category_by_slug(state.mutations.conn, "garten") is not None


def test_unknown_decision_returns_404(web):
    client, _ = web
    rv = client.post(
        "/decisions/9999/re-file",
        json={
            "person_slug": "anna",
            "category_slug": "steuer",
            "filename": "x.pdf",
        },
    )
    assert rv.status_code == 404


def test_refile_when_file_missing_returns_404(web):
    client, decision_id = web
    state = client.application.config["AIDO_STATE"]
    d = get_decision(state.mutations.conn, decision_id)
    # Delete the filed PDF on disk
    Path(d.filed_path).unlink()
    rv = client.post(
        f"/decisions/{decision_id}/re-file",
        json={
            "person_slug": "anna",
            "category_slug": "steuer",
            "filename": "x.pdf",
        },
    )
    assert rv.status_code == 404


def test_refile_with_missing_field_returns_400(web):
    client, decision_id = web
    rv = client.post(f"/decisions/{decision_id}/re-file", json={"person_slug": "anna"})
    assert rv.status_code == 400


def test_refile_with_unknown_person_slug_returns_400(web):
    """An unknown person slug must abort before any DB mutation occurs."""
    client, decision_id = web
    state = client.application.config["AIDO_STATE"]
    before = get_decision(state.mutations.conn, decision_id)
    rv = client.post(
        f"/decisions/{decision_id}/re-file",
        json={
            "person_slug": "nonexistent_person",
            "category_slug": "steuer",
            "filename": "x.pdf",
        },
    )
    assert rv.status_code == 400
    # No mutation: decision still points at the original filed_path.
    after = get_decision(state.mutations.conn, decision_id)
    assert after.filed_path == before.filed_path
    assert list_actions_for_decision(state.mutations.conn, decision_id) == []


def test_refile_with_unknown_category_slug_returns_400(web):
    """An unknown category slug must abort before any DB mutation occurs."""
    client, decision_id = web
    state = client.application.config["AIDO_STATE"]
    before = get_decision(state.mutations.conn, decision_id)
    rv = client.post(
        f"/decisions/{decision_id}/re-file",
        json={
            "person_slug": "anna",
            "category_slug": "nonexistent_cat",
            "filename": "x.pdf",
        },
    )
    assert rv.status_code == 400
    after = get_decision(state.mutations.conn, decision_id)
    assert after.filed_path == before.filed_path
    assert list_actions_for_decision(state.mutations.conn, decision_id) == []


def test_post_rename_renames_in_place_and_audits(web):
    """Rename endpoint moves the on-disk file and emits a RENAME audit row."""
    client, decision_id = web
    state = client.application.config["AIDO_STATE"]
    before = get_decision(state.mutations.conn, decision_id)
    rv = client.post(
        f"/decisions/{decision_id}/rename",
        json={"filename": "renamed.pdf", "note": "tidy"},
    )
    assert rv.status_code == 200
    assert rv.get_json() == {"ok": True}
    after = get_decision(state.mutations.conn, decision_id)
    # Same parent directory, new filename.
    assert Path(after.filed_path).parent == Path(before.filed_path).parent
    assert Path(after.filed_path).name == "renamed.pdf"
    assert Path(after.filed_path).exists()
    assert not Path(before.filed_path).exists()
    [audit] = list_actions_for_decision(state.mutations.conn, decision_id)
    assert audit.action == ManualAction.RENAME
    assert audit.note == "tidy"


def test_post_rename_strips_path_components_from_filename(web):
    """Filename input must be reduced to its basename (no traversal)."""
    client, decision_id = web
    state = client.application.config["AIDO_STATE"]
    rv = client.post(
        f"/decisions/{decision_id}/rename",
        json={"filename": "../../../evil.pdf"},
    )
    assert rv.status_code == 200
    after = get_decision(state.mutations.conn, decision_id)
    assert Path(after.filed_path).name == "evil.pdf"
    # File stayed inside the archive root.
    assert str(Path(after.filed_path).resolve()).startswith(str(state.archive_root.resolve()))


def test_post_rename_unknown_decision_returns_404(web):
    """Rename against a nonexistent decision returns 404 from the ValueError handler."""
    client, _ = web
    rv = client.post("/decisions/9999/rename", json={"filename": "x.pdf"})
    assert rv.status_code == 404


def test_post_rename_missing_field_returns_400(web):
    """Missing 'filename' field returns 400 from the KeyError handler."""
    client, decision_id = web
    rv = client.post(f"/decisions/{decision_id}/rename", json={})
    assert rv.status_code == 400


def test_post_rename_when_file_missing_returns_404(web):
    """If the on-disk file is gone, rename returns 404 via FileNotFoundError handler."""
    client, decision_id = web
    state = client.application.config["AIDO_STATE"]
    d = get_decision(state.mutations.conn, decision_id)
    Path(d.filed_path).unlink()
    rv = client.post(
        f"/decisions/{decision_id}/rename",
        json={"filename": "renamed.pdf"},
    )
    assert rv.status_code == 404


def test_post_delete_unknown_decision_returns_404(web):
    """delete on a nonexistent decision id returns 404."""
    client, _ = web
    rv = client.post("/decisions/9999/delete", json={})
    assert rv.status_code == 404


def test_post_delete_handles_empty_body(web):
    """delete tolerates a request with no JSON body at all."""
    client, decision_id = web
    rv = client.post(f"/decisions/{decision_id}/delete")
    assert rv.status_code == 200


def test_post_approve_unknown_decision_returns_404(web):
    """approve on a nonexistent decision id returns 404."""
    client, _ = web
    rv = client.post("/decisions/9999/approve", json={})
    assert rv.status_code == 404


def test_post_approve_handles_empty_body(web):
    """approve tolerates a request with no JSON body at all."""
    client, decision_id = web
    rv = client.post(f"/decisions/{decision_id}/approve")
    assert rv.status_code == 200


def test_post_promote_category_unknown_decision_returns_404(web):
    """promote-category on a nonexistent decision id returns 404."""
    client, _ = web
    rv = client.post(
        "/decisions/9999/promote-category",
        json={
            "new_category_slug": "garten",
            "new_category_display_name": "Garten",
            "person_slug": "timo",
            "filename": "x.pdf",
        },
    )
    assert rv.status_code == 404


def test_post_promote_category_missing_field_returns_400(web):
    """Missing required field in promote-category body returns 400 via KeyError."""
    client, decision_id = web
    rv = client.post(
        f"/decisions/{decision_id}/promote-category",
        json={"new_category_slug": "garten"},  # missing display_name, person_slug, filename
    )
    assert rv.status_code == 400


def test_post_promote_category_unknown_person_returns_400(web):
    """promote-category with an unknown person slug aborts with 400."""
    client, decision_id = web
    state = client.application.config["AIDO_STATE"]
    rv = client.post(
        f"/decisions/{decision_id}/promote-category",
        json={
            "new_category_slug": "garten",
            "new_category_display_name": "Garten",
            "person_slug": "nonexistent",
            "filename": "x.pdf",
        },
    )
    assert rv.status_code == 400
    # No category created (the abort fires before promote_category runs).
    from aido.store.taxonomy import get_category_by_slug

    assert get_category_by_slug(state.mutations.conn, "garten") is None


def test_post_promote_category_when_file_missing_returns_404(web):
    """If the filed PDF is gone, promote-category surfaces FileNotFoundError as 404."""
    client, decision_id = web
    state = client.application.config["AIDO_STATE"]
    d = get_decision(state.mutations.conn, decision_id)
    Path(d.filed_path).unlink()
    rv = client.post(
        f"/decisions/{decision_id}/promote-category",
        json={
            "new_category_slug": "garten",
            "new_category_display_name": "Garten",
            "person_slug": "timo",
            "filename": "x.pdf",
        },
    )
    assert rv.status_code == 404


def test_post_refile_when_file_missing_uses_filenotfound_branch(web):
    """re-file surfaces missing-on-disk as 404 (FileNotFoundError handler)."""
    # This duplicates test_refile_when_file_missing_returns_404 above but
    # asserts the audit log stayed empty, isolating the error-path semantics.
    client, decision_id = web
    state = client.application.config["AIDO_STATE"]
    d = get_decision(state.mutations.conn, decision_id)
    Path(d.filed_path).unlink()
    rv = client.post(
        f"/decisions/{decision_id}/re-file",
        json={
            "person_slug": "anna",
            "category_slug": "steuer",
            "filename": "x.pdf",
        },
    )
    assert rv.status_code == 404
    assert list_actions_for_decision(state.mutations.conn, decision_id) == []
