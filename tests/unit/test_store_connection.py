from pathlib import Path

import pytest

from aido.store.connection import connect
from aido.store.migrations import init_db


def test_connect_creates_file(tmp_path: Path):
    db = tmp_path / "aido.sqlite"
    with connect(db) as conn:
        cur = conn.execute("SELECT 1")
        row = cur.fetchone()
        assert row[0] == 1
    assert db.exists()


def test_foreign_keys_are_enabled(tmp_path: Path):
    with connect(tmp_path / "x.sqlite") as conn:
        ((on,),) = list(conn.execute("PRAGMA foreign_keys"))
        assert on == 1


def test_journal_mode_is_wal(tmp_path: Path):
    with connect(tmp_path / "x.sqlite") as conn:
        ((mode,),) = list(conn.execute("PRAGMA journal_mode"))
        assert mode == "wal"


def test_init_db_creates_all_tables(tmp_path: Path):
    with connect(tmp_path / "x.sqlite") as conn:
        init_db(conn)
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    expected = {
        "persons",
        "person_aliases",
        "categories",
        "doctypes",
        "decisions",
        "manual_actions",
        "pending_jobs",
        "schema_version",
    }
    assert expected.issubset(tables)


def test_init_db_is_idempotent(tmp_path: Path):
    with connect(tmp_path / "x.sqlite") as conn:
        init_db(conn)
        init_db(conn)  # second call must not raise
        ((v,),) = list(conn.execute("SELECT MAX(version) FROM schema_version"))
        assert v == 1


def test_check_constraint_rejects_bad_status(tmp_path: Path):
    import sqlite3

    with connect(tmp_path / "x.sqlite") as conn:
        init_db(conn)
        conn.execute(
            "INSERT INTO persons(slug, display_name, is_shared) VALUES (?, ?, 0)",
            ("timo", "Timo"),
        )
        conn.execute(
            "INSERT INTO categories(slug, display_name, is_review) VALUES (?, ?, 0)",
            ("rechnungen", "Rechnungen"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO decisions("
                "  created_at, source_hash, source_path, filed_path, person_id, "
                "  category_id, proposed_filename, overall_confidence, "
                "  person_confidence, category_confidence, classifier_model, "
                "  needs_review, status"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "2026-05-17T10:00:00",
                    "h",
                    "/s",
                    "/d",
                    1,
                    1,
                    "x.pdf",
                    0.9,
                    0.9,
                    0.9,
                    "claude-opus-4-7",
                    0,
                    "GARBAGE",
                ),
            )
