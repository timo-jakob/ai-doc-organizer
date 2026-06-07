"""Categories + doctypes repository."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CategoryRow:
    id: int
    slug: str
    display_name: str
    description: str | None
    is_review: bool
    is_active: bool


@dataclass(frozen=True, slots=True)
class DoctypeRow:
    id: int
    slug: str
    display_name: str
    description: str | None
    is_active: bool


def _row_to_category(row: sqlite3.Row) -> CategoryRow:
    return CategoryRow(
        id=row["id"],
        slug=row["slug"],
        display_name=row["display_name"],
        description=row["description"],
        is_review=bool(row["is_review"]),
        is_active=bool(row["is_active"]),
    )


def _row_to_doctype(row: sqlite3.Row) -> DoctypeRow:
    return DoctypeRow(
        id=row["id"],
        slug=row["slug"],
        display_name=row["display_name"],
        description=row["description"],
        is_active=bool(row["is_active"]),
    )


# Adjacent-string-literal SQL constants — no runtime `+`/f-string so ruff
# S608 + semgrep formatted-sql-query don't misfire. All variable inputs
# flow through `?` placeholders.
_SQL_GET_CATEGORY_BY_ID = (
    "SELECT id, slug, display_name, description, is_review, is_active FROM categories WHERE id = ?"
)
_SQL_GET_CATEGORY_BY_SLUG = (
    "SELECT id, slug, display_name, description, is_review, is_active "
    "FROM categories WHERE slug = ?"
)
_SQL_GET_REVIEW_CATEGORY = (
    "SELECT id, slug, display_name, description, is_review, is_active "
    "FROM categories WHERE is_review = 1 LIMIT 1"
)
_SQL_LIST_CATEGORIES_ACTIVE = (
    "SELECT id, slug, display_name, description, is_review, is_active "
    "FROM categories WHERE is_active = 1 ORDER BY slug"
)
_SQL_LIST_CATEGORIES_ALL = (
    "SELECT id, slug, display_name, description, is_review, is_active FROM categories ORDER BY slug"
)
_SQL_GET_DOCTYPE_BY_ID = (
    "SELECT id, slug, display_name, description, is_active FROM doctypes WHERE id = ?"
)
_SQL_GET_DOCTYPE_BY_SLUG = (
    "SELECT id, slug, display_name, description, is_active FROM doctypes WHERE slug = ?"
)
_SQL_LIST_DOCTYPES_ACTIVE = (
    "SELECT id, slug, display_name, description, is_active "
    "FROM doctypes WHERE is_active = 1 ORDER BY slug"
)
_SQL_LIST_DOCTYPES_ALL = (
    "SELECT id, slug, display_name, description, is_active FROM doctypes ORDER BY slug"
)


def create_category(
    conn: sqlite3.Connection,
    *,
    slug: str,
    display_name: str,
    description: str | None = None,
    is_review: bool = False,
    is_active: bool = True,
) -> CategoryRow:
    cur = conn.execute(
        "INSERT INTO categories(slug, display_name, description, is_review, is_active) "
        "VALUES (?, ?, ?, ?, ?)",
        (slug, display_name, description, int(is_review), int(is_active)),
    )
    row = conn.execute(_SQL_GET_CATEGORY_BY_ID, (cur.lastrowid,)).fetchone()
    return _row_to_category(row)


def get_category_by_slug(conn: sqlite3.Connection, slug: str) -> CategoryRow | None:
    row = conn.execute(_SQL_GET_CATEGORY_BY_SLUG, (slug,)).fetchone()
    return _row_to_category(row) if row else None


def get_review_category(conn: sqlite3.Connection) -> CategoryRow | None:
    row = conn.execute(_SQL_GET_REVIEW_CATEGORY).fetchone()
    return _row_to_category(row) if row else None


def list_categories(
    conn: sqlite3.Connection, *, include_inactive: bool = False
) -> list[CategoryRow]:
    sql = _SQL_LIST_CATEGORIES_ALL if include_inactive else _SQL_LIST_CATEGORIES_ACTIVE
    rows = conn.execute(sql).fetchall()
    return [_row_to_category(r) for r in rows]


def create_doctype(
    conn: sqlite3.Connection,
    *,
    slug: str,
    display_name: str,
    description: str | None = None,
    is_active: bool = True,
) -> DoctypeRow:
    cur = conn.execute(
        "INSERT INTO doctypes(slug, display_name, description, is_active) VALUES (?, ?, ?, ?)",
        (slug, display_name, description, int(is_active)),
    )
    row = conn.execute(_SQL_GET_DOCTYPE_BY_ID, (cur.lastrowid,)).fetchone()
    return _row_to_doctype(row)


def get_doctype_by_slug(conn: sqlite3.Connection, slug: str) -> DoctypeRow | None:
    row = conn.execute(_SQL_GET_DOCTYPE_BY_SLUG, (slug,)).fetchone()
    return _row_to_doctype(row) if row else None


def list_doctypes(conn: sqlite3.Connection, *, include_inactive: bool = False) -> list[DoctypeRow]:
    sql = _SQL_LIST_DOCTYPES_ALL if include_inactive else _SQL_LIST_DOCTYPES_ACTIVE
    rows = conn.execute(sql).fetchall()
    return [_row_to_doctype(r) for r in rows]
