"""DDL bootstrap. v1 has exactly one schema version."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

SCHEMA_VERSION = 1
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def init_db(conn: sqlite3.Connection) -> None:
    """Apply DDL if the database is empty. Idempotent."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()
    if row is None:
        with conn:
            # _SCHEMA_PATH is a package-internal DDL file (schema.sql) resolved relative
            # to this module's location — it is developer-controlled, not user-supplied.
            # executescript() is required for multi-statement DDL and does not support
            # parameterised queries; the input source is not external/user data.
            conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))  # nosonar
            conn.execute(
                "INSERT INTO schema_version(version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, datetime.now(UTC).isoformat()),
            )
        return
    # Already initialised; ensure version row matches expectation.
    current = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    if current != SCHEMA_VERSION:
        raise RuntimeError(f"Unsupported schema version {current!r}; expected {SCHEMA_VERSION}")
