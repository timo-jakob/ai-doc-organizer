"""Decisions repository."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime

from aido.types import DecisionStatus

# Each query below uses adjacent-string-literal concatenation (compile-time)
# rather than runtime `+` so ruff S608 and semgrep's raw-query rules don't
# misfire. All variable inputs flow through `?` placeholders.
_SQL_GET_DECISION = (
    "SELECT id, created_at AS 'created_at [DATETIME]', source_hash, source_path, filed_path, "
    "person_id, category_id, doctype_id, "
    "document_date AS 'document_date [DATE]', counterparty, proposed_filename, "
    "overall_confidence, person_confidence, category_confidence, "
    "reasoning, classifier_model, new_category_proposal, "
    "needs_review, status "
    "FROM decisions WHERE id = ?"
)
_SQL_FIND_BY_SOURCE_HASH = (
    "SELECT id, created_at AS 'created_at [DATETIME]', source_hash, source_path, filed_path, "
    "person_id, category_id, doctype_id, "
    "document_date AS 'document_date [DATE]', counterparty, proposed_filename, "
    "overall_confidence, person_confidence, category_confidence, "
    "reasoning, classifier_model, new_category_proposal, "
    "needs_review, status "
    "FROM decisions WHERE source_hash = ?"
)
_SQL_LIST_RECENT_REVIEW = (
    "SELECT id, created_at AS 'created_at [DATETIME]', source_hash, source_path, filed_path, "
    "person_id, category_id, doctype_id, "
    "document_date AS 'document_date [DATE]', counterparty, proposed_filename, "
    "overall_confidence, person_confidence, category_confidence, "
    "reasoning, classifier_model, new_category_proposal, "
    "needs_review, status "
    "FROM decisions WHERE needs_review = 1 ORDER BY created_at DESC LIMIT ?"
)
_SQL_LIST_RECENT_ALL = (
    "SELECT id, created_at AS 'created_at [DATETIME]', source_hash, source_path, filed_path, "
    "person_id, category_id, doctype_id, "
    "document_date AS 'document_date [DATE]', counterparty, proposed_filename, "
    "overall_confidence, person_confidence, category_confidence, "
    "reasoning, classifier_model, new_category_proposal, "
    "needs_review, status "
    "FROM decisions ORDER BY created_at DESC LIMIT ?"
)


@dataclass(frozen=True)
class NewDecision:
    created_at: datetime
    source_hash: str
    source_path: str
    filed_path: str
    person_id: int
    category_id: int
    doctype_id: int | None
    document_date: date | None
    counterparty: str | None
    proposed_filename: str
    overall_confidence: float
    person_confidence: float
    category_confidence: float
    reasoning: str | None
    classifier_model: str
    new_category_proposal: str | None
    needs_review: bool
    status: DecisionStatus


@dataclass(frozen=True)
class DecisionRow:
    id: int
    created_at: datetime
    source_hash: str
    source_path: str
    filed_path: str
    person_id: int
    category_id: int
    doctype_id: int | None
    document_date: date | None
    counterparty: str | None
    proposed_filename: str
    overall_confidence: float
    person_confidence: float
    category_confidence: float
    reasoning: str | None
    classifier_model: str
    new_category_proposal: str | None
    needs_review: bool
    status: DecisionStatus


@dataclass(frozen=True)
class DecisionUpdate:
    """Fields a manual action might change. None = leave alone."""

    filed_path: str | None = None
    person_id: int | None = None
    category_id: int | None = None
    doctype_id: int | None = None
    proposed_filename: str | None = None
    needs_review: bool | None = None
    status: DecisionStatus | None = None


def _row_to_decision(row: sqlite3.Row) -> DecisionRow:
    return DecisionRow(
        id=row["id"],
        created_at=row["created_at"],
        source_hash=row["source_hash"],
        source_path=row["source_path"],
        filed_path=row["filed_path"],
        person_id=row["person_id"],
        category_id=row["category_id"],
        doctype_id=row["doctype_id"],
        document_date=row["document_date"],
        counterparty=row["counterparty"],
        proposed_filename=row["proposed_filename"],
        overall_confidence=row["overall_confidence"],
        person_confidence=row["person_confidence"],
        category_confidence=row["category_confidence"],
        reasoning=row["reasoning"],
        classifier_model=row["classifier_model"],
        new_category_proposal=row["new_category_proposal"],
        needs_review=bool(row["needs_review"]),
        status=DecisionStatus(row["status"]),
    )


def insert_decision(conn: sqlite3.Connection, d: NewDecision) -> int:
    cur = conn.execute(
        "INSERT INTO decisions("
        "  created_at, source_hash, source_path, filed_path, person_id, category_id, "
        "  doctype_id, document_date, counterparty, proposed_filename, "
        "  overall_confidence, person_confidence, category_confidence, "
        "  reasoning, classifier_model, new_category_proposal, "
        "  needs_review, status"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            d.created_at,
            d.source_hash,
            d.source_path,
            d.filed_path,
            d.person_id,
            d.category_id,
            d.doctype_id,
            d.document_date,
            d.counterparty,
            d.proposed_filename,
            d.overall_confidence,
            d.person_confidence,
            d.category_confidence,
            d.reasoning,
            d.classifier_model,
            d.new_category_proposal,
            int(d.needs_review),
            d.status.value,
        ),
    )
    return cur.lastrowid


def get_decision(conn: sqlite3.Connection, decision_id: int) -> DecisionRow | None:
    row = conn.execute(_SQL_GET_DECISION, (decision_id,)).fetchone()
    return _row_to_decision(row) if row else None


def find_by_source_hash(conn: sqlite3.Connection, source_hash: str) -> DecisionRow | None:
    row = conn.execute(_SQL_FIND_BY_SOURCE_HASH, (source_hash,)).fetchone()
    return _row_to_decision(row) if row else None


def list_recent(
    conn: sqlite3.Connection,
    *,
    limit: int = 50,
    needs_review_only: bool = False,
) -> list[DecisionRow]:
    sql = _SQL_LIST_RECENT_REVIEW if needs_review_only else _SQL_LIST_RECENT_ALL
    rows = conn.execute(sql, (limit,)).fetchall()
    return [_row_to_decision(r) for r in rows]


def count_needs_review(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) FROM decisions WHERE needs_review = 1").fetchone()
    return row[0]


def update_decision(conn: sqlite3.Connection, decision_id: int, update: DecisionUpdate) -> None:
    sets: list[str] = []
    params: list[object] = []
    if update.filed_path is not None:
        sets.append("filed_path = ?")
        params.append(update.filed_path)
    if update.person_id is not None:
        sets.append("person_id = ?")
        params.append(update.person_id)
    if update.category_id is not None:
        sets.append("category_id = ?")
        params.append(update.category_id)
    if update.doctype_id is not None:
        sets.append("doctype_id = ?")
        params.append(update.doctype_id)
    if update.proposed_filename is not None:
        sets.append("proposed_filename = ?")
        params.append(update.proposed_filename)
    if update.needs_review is not None:
        sets.append("needs_review = ?")
        params.append(int(update.needs_review))
    if update.status is not None:
        sets.append("status = ?")
        params.append(update.status.value)
    if not sets:
        return
    params.append(decision_id)
    # `sets` contains only literal `col = ?` fragments built from the kwarg
    # checks above; all values flow through `?` placeholders in `params`.
    # ruff S608 fires on the runtime concat — annotation justified because
    # the dynamic part is server-built fragments, not user input.
    sql = "UPDATE decisions SET " + ", ".join(sets) + " WHERE id = ?"  # noqa: S608
    # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
    conn.execute(sql, params)
