"""Retry queue for classifier failures."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

_COLS = (
    "id, source_path, source_hash, attempts, "
    "next_attempt_at AS 'next_attempt_at [DATETIME]', "
    "last_error, "
    "created_at AS 'created_at [DATETIME]'"
)
# Adjacent-string-literal concatenation (compile-time) — no runtime `+` or
# f-string so ruff S608 + semgrep formatted-sql-query don't misfire. All
# variable inputs flow through `?` placeholders.
_SQL_CLAIM_DUE = (
    "SELECT id, source_path, source_hash, attempts, "
    "next_attempt_at AS 'next_attempt_at [DATETIME]', "
    "last_error, "
    "created_at AS 'created_at [DATETIME]' "
    "FROM pending_jobs WHERE next_attempt_at <= ? "
    "ORDER BY next_attempt_at ASC LIMIT ?"
)


@dataclass(frozen=True, slots=True)
class PendingJobRow:
    id: int
    source_path: str
    source_hash: str
    attempts: int
    next_attempt_at: datetime
    last_error: str | None
    created_at: datetime


def _row_to_job(row: sqlite3.Row) -> PendingJobRow:
    return PendingJobRow(
        id=row["id"],
        source_path=row["source_path"],
        source_hash=row["source_hash"],
        attempts=row["attempts"],
        next_attempt_at=row["next_attempt_at"],
        last_error=row["last_error"],
        created_at=row["created_at"],
    )


def enqueue_pending(
    conn: sqlite3.Connection,
    *,
    source_path: str,
    source_hash: str,
    next_attempt_at: datetime,
    created_at: datetime,
) -> int:
    cur = conn.execute(
        "INSERT INTO pending_jobs(source_path, source_hash, next_attempt_at, created_at) "
        "VALUES (?, ?, ?, ?)",
        (source_path, source_hash, next_attempt_at, created_at),
    )
    return cur.lastrowid


def claim_due(conn: sqlite3.Connection, *, now: datetime, limit: int = 10) -> list[PendingJobRow]:
    rows = conn.execute(_SQL_CLAIM_DUE, (now, limit)).fetchall()
    return [_row_to_job(r) for r in rows]


def record_attempt(
    conn: sqlite3.Connection,
    job_id: int,
    *,
    error: str,
    next_attempt_at: datetime,
) -> None:
    conn.execute(
        "UPDATE pending_jobs SET attempts = attempts + 1, last_error = ?, "
        "next_attempt_at = ? WHERE id = ?",
        (error, next_attempt_at, job_id),
    )


def delete_pending(conn: sqlite3.Connection, job_id: int) -> None:
    conn.execute("DELETE FROM pending_jobs WHERE id = ?", (job_id,))
