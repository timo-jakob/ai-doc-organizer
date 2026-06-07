"""Audit log of human-driven mutations."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from aido.types import ManualAction

# Adjacent-string-literal concatenation — no runtime `+`/f-string for the
# linters to flag. All variable inputs flow through `?` placeholders.
_SQL_LIST_ACTIONS_FOR_DECISION = (
    "SELECT id, decision_id, action, before_path, after_path, "
    "before_person_id, after_person_id, before_category_id, after_category_id, "
    "created_at AS 'created_at [DATETIME]', note "
    "FROM manual_actions WHERE decision_id = ? ORDER BY created_at ASC"
)


@dataclass(frozen=True, slots=True)
class NewManualAction:
    decision_id: int
    action: ManualAction
    before_path: str
    after_path: str | None
    before_person_id: int | None
    after_person_id: int | None
    before_category_id: int | None
    after_category_id: int | None
    created_at: datetime
    note: str | None


@dataclass(frozen=True, slots=True)
class ManualActionRow:
    id: int
    decision_id: int
    action: ManualAction
    before_path: str
    after_path: str | None
    before_person_id: int | None
    after_person_id: int | None
    before_category_id: int | None
    after_category_id: int | None
    created_at: datetime
    note: str | None


def _row_to_action(row: sqlite3.Row) -> ManualActionRow:
    return ManualActionRow(
        id=row["id"],
        decision_id=row["decision_id"],
        action=ManualAction(row["action"]),
        before_path=row["before_path"],
        after_path=row["after_path"],
        before_person_id=row["before_person_id"],
        after_person_id=row["after_person_id"],
        before_category_id=row["before_category_id"],
        after_category_id=row["after_category_id"],
        created_at=row["created_at"],
        note=row["note"],
    )


def insert_manual_action(conn: sqlite3.Connection, a: NewManualAction) -> int:
    cur = conn.execute(
        "INSERT INTO manual_actions("
        "  decision_id, action, before_path, after_path, "
        "  before_person_id, after_person_id, before_category_id, after_category_id, "
        "  created_at, note"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            a.decision_id,
            a.action.value,
            a.before_path,
            a.after_path,
            a.before_person_id,
            a.after_person_id,
            a.before_category_id,
            a.after_category_id,
            a.created_at,
            a.note,
        ),
    )
    return cur.lastrowid


def list_actions_for_decision(conn: sqlite3.Connection, decision_id: int) -> list[ManualActionRow]:
    rows = conn.execute(_SQL_LIST_ACTIONS_FOR_DECISION, (decision_id,)).fetchall()
    return [_row_to_action(r) for r in rows]
