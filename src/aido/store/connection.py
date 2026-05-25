"""SQLite connection setup: pragmas, type adapters, helper functions."""

from __future__ import annotations

import contextlib
import sqlite3
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path


def _adapt_datetime(d: datetime) -> str:
    return d.isoformat(timespec="microseconds")


def _adapt_date(d: date) -> str:
    return d.isoformat()


def _convert_datetime(b: bytes) -> datetime:
    return datetime.fromisoformat(b.decode())


def _convert_date(b: bytes) -> date:
    return date.fromisoformat(b.decode())


_REGISTERED = False


def _register_adapters_once() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    sqlite3.register_adapter(datetime, _adapt_datetime)
    sqlite3.register_adapter(date, _adapt_date)
    sqlite3.register_converter("DATETIME", _convert_datetime)
    sqlite3.register_converter("DATE", _convert_date)
    _REGISTERED = True


@contextlib.contextmanager
def connect(path: Path | str) -> Iterator[sqlite3.Connection]:
    """Open a connection with pragmas + type detection configured.

    Yields a context-managed `sqlite3.Connection`. Commits on clean exit,
    rolls back on exception.
    """
    _register_adapters_once()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        str(path),
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        isolation_level=None,  # autocommit; we manage transactions ourselves
        check_same_thread=False,  # daemon worker + Flask handlers share one connection
    )
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA busy_timeout = 5000")  # wait up to 5s on writer contention
        conn.row_factory = sqlite3.Row
        yield conn
    finally:
        conn.close()
