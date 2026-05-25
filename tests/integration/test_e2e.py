import time
from datetime import date
from pathlib import Path

from aido.classifier.fake import FakeClassifier
from aido.daemon import Daemon
from aido.store.connection import connect
from aido.store.decisions import list_recent
from aido.store.migrations import init_db
from aido.store.persons import create_person
from aido.store.taxonomy import create_category, create_doctype
from aido.types import ClassificationResult
from aido.webui.app import WebState, create_app
from tests.fixtures import synth_pdf


def _result(person="timo", cat="rechnungen", filename="2026-03-12_rechnung_telekom.pdf"):
    return ClassificationResult(
        person_slug=person,
        category_slug=cat,
        doctype_slug="rechnung",
        document_date=date(2026, 3, 12),
        counterparty="telekom",
        proposed_filename=filename,
        overall_confidence=0.93,
        person_confidence=0.95,
        category_confidence=0.91,
        new_category_proposal=None,
        reasoning="recipient Timo; sender Telekom",
    )


def test_e2e_drop_file_audit_refile(tmp_path: Path):
    archive = tmp_path / "archive"
    archive.mkdir()
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    db = tmp_path / "x.sqlite"
    with connect(db) as conn:
        init_db(conn)
        create_person(conn, slug="timo", display_name="Timo")
        create_person(conn, slug="anna", display_name="Anna")
        create_person(conn, slug="shared", display_name="Shared", is_shared=True)
        create_category(conn, slug="rechnungen", display_name="Rechnungen")
        create_category(conn, slug="steuer", display_name="Steuer")
        create_category(conn, slug="_review", display_name="_review", is_review=True)
        create_doctype(conn, slug="rechnung", display_name="Rechnung")
        create_doctype(conn, slug="letter", display_name="Letter")

    fake = FakeClassifier(results=[_result()])

    daemon = Daemon(
        db_path=db,
        archive_root=archive,
        inbox=inbox,
        classifier_factory=lambda conn: fake,
        threshold=0.75,
        classifier_model="claude-opus-4-7",
        pidfile=tmp_path / "aido.pid",
        poll_interval=0.2,
        stabilize_seconds=0.0,
    )
    daemon.start()
    try:
        pdf = synth_pdf(inbox / "scan001.pdf", text=["Telekom Rechnung", "Timo Jakob"])
        # Wait for the daemon to file it (expected within ~3s).
        decision_id = None
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with connect(db) as conn:
                rows = list_recent(conn, limit=1)
                if rows:
                    decision_id = rows[0].id
                    break
            time.sleep(0.2)
        assert decision_id is not None, "daemon never filed the dropped PDF"

        # Run the web UI against the daemon's mutation context.
        state = WebState(
            db_path=db,
            archive_root=archive,
            mutations=daemon._mutations,  # type: ignore[attr-defined]
            health=daemon.health,
        )
        app = create_app(state)
        client = app.test_client()

        # Confirm the detail page renders.
        rv = client.get(f"/decisions/{decision_id}")
        assert rv.status_code == 200

        # Re-file under anna/steuer.
        rv = client.post(
            f"/decisions/{decision_id}/re-file",
            json={
                "person_slug": "anna",
                "category_slug": "steuer",
                "filename": "2026-03-12_rechnung_telekom.pdf",
            },
        )
        assert rv.status_code == 200, rv.data

        # Verify the file actually moved.
        moved = archive / "anna" / "steuer" / "2026-03-12_rechnung_telekom.pdf"
        assert moved.exists()
    finally:
        daemon.stop()
