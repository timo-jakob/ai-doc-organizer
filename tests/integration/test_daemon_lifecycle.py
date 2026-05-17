# tests/integration/test_daemon_lifecycle.py
import time
from datetime import date
from pathlib import Path

import pytest

from aido.classifier.fake import FakeClassifier
from aido.daemon import Daemon, HealthStatus
from aido.store.connection import connect
from aido.store.decisions import find_by_source_hash
from aido.store.migrations import init_db
from aido.store.persons import create_person
from aido.store.taxonomy import create_category, create_doctype
from aido.types import ClassificationResult
from tests.fixtures import synth_pdf


def _result():
    return ClassificationResult(
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
        reasoning="r",
    )


@pytest.fixture
def seeded(tmp_path):
    archive = tmp_path / "archive"
    inbox = tmp_path / "inbox"
    archive.mkdir()
    inbox.mkdir()
    db = tmp_path / "x.sqlite"
    with connect(db) as conn:
        init_db(conn)
        create_person(conn, slug="timo", display_name="Timo Jakob")
        create_person(conn, slug="shared", display_name="Shared", is_shared=True)
        create_category(conn, slug="rechnungen", display_name="Rechnungen")
        create_category(conn, slug="_review", display_name="_review", is_review=True)
        create_doctype(conn, slug="rechnung", display_name="Rechnung")
        create_doctype(conn, slug="letter", display_name="Letter")
    return {"db": db, "archive": archive, "inbox": inbox, "tmp": tmp_path}


def test_daemon_files_a_pdf_dropped_in_inbox(seeded):
    fake = FakeClassifier(results=[_result()])
    daemon = Daemon(
        db_path=seeded["db"],
        archive_root=seeded["archive"],
        inbox=seeded["inbox"],
        classifier_factory=lambda conn: fake,
        threshold=0.75,
        classifier_model="claude-opus-4-7",
        poll_interval=0.2,
        stabilize_seconds=0.0,
        pidfile=seeded["tmp"] / "aido.pid",
    )
    daemon.start()
    try:
        pdf = synth_pdf(seeded["inbox"] / "scan001.pdf", text=["Telekom Rechnung"])
        # Wait up to 5s for the worker to file it.
        deadline = time.monotonic() + 5
        decision = None
        while time.monotonic() < deadline:
            with connect(seeded["db"]) as conn:
                from aido.pdf.hash import sha256_of_file
                if pdf.exists():
                    h = sha256_of_file(pdf)
                else:
                    # Already moved — scan archive folder for files
                    moved = list(seeded["archive"].rglob("*.pdf"))
                    if moved:
                        h = sha256_of_file(moved[0])
                    else:
                        h = ""
                if h:
                    decision = find_by_source_hash(conn, h)
                if decision is not None:
                    break
            time.sleep(0.2)
        assert decision is not None
        assert daemon.health.status == HealthStatus.OK
    finally:
        daemon.stop()


def test_daemon_pidfile_prevents_double_start(seeded):
    daemon1 = Daemon(
        db_path=seeded["db"],
        archive_root=seeded["archive"],
        inbox=seeded["inbox"],
        classifier_factory=lambda conn: FakeClassifier(results=[]),
        threshold=0.75,
        classifier_model="m",
        pidfile=seeded["tmp"] / "aido.pid",
        poll_interval=0.5,
    )
    daemon1.start()
    try:
        daemon2 = Daemon(
            db_path=seeded["db"],
            archive_root=seeded["archive"],
            inbox=seeded["inbox"],
            classifier_factory=lambda conn: FakeClassifier(results=[]),
            threshold=0.75,
            classifier_model="m",
            pidfile=seeded["tmp"] / "aido.pid",
            poll_interval=0.5,
        )
        with pytest.raises(RuntimeError, match="already running"):
            daemon2.start()
    finally:
        daemon1.stop()
