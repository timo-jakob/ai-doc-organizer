"""Persons + aliases repository."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from aido.filing.alias import alias_normalize


@dataclass(frozen=True, slots=True)
class PersonRow:
    id: int
    slug: str
    display_name: str
    is_shared: bool
    is_active: bool


@dataclass(frozen=True, slots=True)
class AliasRow:
    id: int
    person_id: int
    alias: str
    alias_normalized: str


def _row_to_person(row: sqlite3.Row) -> PersonRow:
    return PersonRow(
        id=row["id"],
        slug=row["slug"],
        display_name=row["display_name"],
        is_shared=bool(row["is_shared"]),
        is_active=bool(row["is_active"]),
    )


def _row_to_alias(row: sqlite3.Row) -> AliasRow:
    return AliasRow(
        id=row["id"],
        person_id=row["person_id"],
        alias=row["alias"],
        alias_normalized=row["alias_normalized"],
    )


def create_person(
    conn: sqlite3.Connection,
    *,
    slug: str,
    display_name: str,
    is_shared: bool = False,
    is_active: bool = True,
) -> PersonRow:
    cur = conn.execute(
        "INSERT INTO persons(slug, display_name, is_shared, is_active) VALUES (?, ?, ?, ?)",
        (slug, display_name, int(is_shared), int(is_active)),
    )
    return _person_by_id(conn, cur.lastrowid)


def _person_by_id(conn: sqlite3.Connection, person_id: int) -> PersonRow:
    row = conn.execute(
        "SELECT id, slug, display_name, is_shared, is_active FROM persons WHERE id = ?",
        (person_id,),
    ).fetchone()
    assert row is not None
    return _row_to_person(row)


def get_person_by_slug(conn: sqlite3.Connection, slug: str) -> PersonRow | None:
    row = conn.execute(
        "SELECT id, slug, display_name, is_shared, is_active FROM persons WHERE slug = ?",
        (slug,),
    ).fetchone()
    return _row_to_person(row) if row else None


def list_persons(conn: sqlite3.Connection, *, include_inactive: bool = False) -> list[PersonRow]:
    where = "" if include_inactive else "WHERE is_active = 1"
    rows = conn.execute(
        f"SELECT id, slug, display_name, is_shared, is_active FROM persons {where} ORDER BY slug"
    ).fetchall()
    return [_row_to_person(r) for r in rows]


def add_alias(conn: sqlite3.Connection, *, person_id: int, alias: str) -> AliasRow:
    normalized = alias_normalize(alias)
    # Check if this normalized alias exists for this person
    existing = conn.execute(
        "SELECT id, person_id, alias, alias_normalized FROM person_aliases "
        "WHERE person_id = ? AND alias_normalized = ?",
        (person_id, normalized),
    ).fetchone()
    if existing:
        return _row_to_alias(existing)

    # Check if this normalized alias exists for a different person
    other_person = conn.execute(
        "SELECT person_id FROM person_aliases WHERE alias_normalized = ? LIMIT 1",
        (normalized,),
    ).fetchone()
    if other_person:
        raise sqlite3.IntegrityError("UNIQUE constraint failed: person_aliases.alias_normalized")

    cur = conn.execute(
        "INSERT INTO person_aliases(person_id, alias, alias_normalized) VALUES (?, ?, ?)",
        (person_id, alias, normalized),
    )
    row = conn.execute(
        "SELECT id, person_id, alias, alias_normalized FROM person_aliases WHERE id = ?",
        (cur.lastrowid,),
    ).fetchone()
    return _row_to_alias(row)


def list_aliases_for(conn: sqlite3.Connection, person_id: int) -> list[AliasRow]:
    rows = conn.execute(
        "SELECT id, person_id, alias, alias_normalized FROM person_aliases "
        "WHERE person_id = ? ORDER BY alias",
        (person_id,),
    ).fetchall()
    return [_row_to_alias(r) for r in rows]


def find_person_by_alias(conn: sqlite3.Connection, alias: str) -> PersonRow | None:
    normalized = alias_normalize(alias)
    row = conn.execute(
        "SELECT p.id, p.slug, p.display_name, p.is_shared, p.is_active "
        "FROM persons p JOIN person_aliases a ON a.person_id = p.id "
        "WHERE a.alias_normalized = ?",
        (normalized,),
    ).fetchone()
    return _row_to_person(row) if row else None
