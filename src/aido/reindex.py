"""Reconcile the archive tree against the `decisions` table.

Backs `aido rebuild-index`: after manual filesystem edits, a `_review/`
cleanup, or a fresh deploy that mirrored an existing archive, the operator
wants the decisions index to match what is actually on disk without
re-running the classifier.

The reconcile is planned from reads (filesystem walk + one SELECT) and then
applied, with both stages inside a single BEGIN IMMEDIATE transaction so a
concurrent writer (the daemon worker shares this DB in production) cannot
change rows between planning and apply. Any error rolls back and leaves the
DB untouched.
"""

from __future__ import annotations

import contextlib
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from aido.pdf.hash import sha256_of_file
from aido.store.decisions import (
    DecisionUpdate,
    NewDecision,
    insert_decision,
    update_decision,
)
from aido.store.persons import PersonRow, list_persons
from aido.store.taxonomy import CategoryRow, get_review_category, list_categories
from aido.types import DecisionStatus

DISCOVERED_REASONING = "rebuild-index: discovered on disk"

# If more than this share of existing rows would be flagged failed, the
# archive is more likely mis-mounted or half-synced than mass-deleted.
_MASS_FLAG_THRESHOLD = 0.5


class ReconcileError(Exception):
    """Reconciliation cannot proceed; the DB has not been modified."""


@dataclass(frozen=True, slots=True)
class ReconcileSummary:
    added: int
    flagged: int
    in_sync: int
    # Previously-failed rows whose file exists again (in place or relinked),
    # restored to human_filed.
    recovered: int = 0
    # Same-content PDFs that could not get their own row because their
    # source_hash already belongs to a row whose file still exists (the
    # decisions.source_hash column is UNIQUE). Surfaced as warnings.
    skipped_duplicates: tuple[str, ...] = field(default=())
    # PDFs that could not be hashed (unreadable / vanished mid-walk),
    # skipped rather than aborting the whole reconcile. Surfaced as warnings.
    skipped_unreadable: tuple[str, ...] = field(default=())


def validate_archive_root(archive_root: Path) -> None:
    """Reject an unusable archive root before any DB is opened."""
    if not archive_root.is_dir():
        raise ReconcileError(f"archive root is not a directory: {archive_root}")
    if not os.access(archive_root, os.R_OK | os.X_OK):
        raise ReconcileError(f"archive root is not readable: {archive_root}")


def reconcile(conn: sqlite3.Connection, archive_root: Path) -> ReconcileSummary:
    """Walk `archive_root` and reconcile it against the `decisions` table.

    - PDFs on disk with no matching `filed_path` get a synthetic
      `human_filed` row (person/category inferred from the
      `<person>/<category>/` path layout, falling back to the shared
      person / `_review` category like the worker pipeline does).
    - A discovered PDF whose content hash already has a row pointing at a
      now-missing file is treated as manually moved: the existing row is
      re-pointed instead of inserting (source_hash is UNIQUE).
    - Rows whose `filed_path` no longer exists are flagged `failed`;
      `failed` rows whose file exists again are restored to `human_filed`.

    Planning and applying share one BEGIN IMMEDIATE transaction, so a
    concurrent DB writer cannot change rows between the planning snapshot
    and the writes here. The transaction does not lock the filesystem: a
    daemon filing documents mid-walk can still race the discovery, so
    rebuild-index is best run while the daemon is idle. Raises
    :class:`ReconcileError` (rolling
    back, with the DB unmodified) when the root is unusable, the DB lacks
    the rows needed to satisfy foreign keys, or the mass-flag guard trips.
    """
    validate_archive_root(archive_root)

    # The connection runs in autocommit (isolation_level=None), so the
    # explicit BEGIN..COMMIT is what makes the reconcile atomic. IMMEDIATE
    # takes the write lock before the first read: planning from an
    # unguarded snapshot would let the daemon worker re-file a document
    # between snapshot and apply and get its valid row flagged as failed.
    conn.execute("BEGIN IMMEDIATE")
    try:
        plan = _plan(conn, archive_root)
        _check_mass_flag(plan)
        _apply(conn, plan)
    except BaseException:
        # A failing ROLLBACK (connection torn down, disk error) must not
        # mask the root cause the operator needs to see.
        with contextlib.suppress(sqlite3.Error):
            conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")
    return plan.summary()


@dataclass(frozen=True, slots=True)
class _ReconcilePlan:
    """All writes derived from one consistent read of the DB and the disk."""

    relinks: tuple[tuple[int, DecisionUpdate, bool], ...]  # (id, update, was failed)
    inserts: tuple[NewDecision, ...]
    orphan_ids: tuple[int, ...]
    recovered_ids: tuple[int, ...]
    duplicates: tuple[str, ...]
    unreadable: tuple[str, ...]
    in_sync: int
    total_rows: int

    def summary(self) -> ReconcileSummary:
        recovered = len(self.recovered_ids) + sum(
            1 for _, _, was_failed in self.relinks if was_failed
        )
        return ReconcileSummary(
            added=len(self.inserts),
            flagged=len(self.orphan_ids),
            in_sync=self.in_sync,
            recovered=recovered,
            skipped_duplicates=self.duplicates,
            skipped_unreadable=self.unreadable,
        )


def _canon(path: str | Path) -> str:
    """Collapse a path to one canonical spelling for identity comparison."""
    return os.path.normcase(str(Path(path).resolve()))


def _file_key(path: str | Path) -> tuple[int, int] | None:
    """Device/inode identity, or None when the file cannot be stat'd."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return st.st_dev, st.st_ino


def _row_state(path: str) -> str:
    """'present' | 'missing' | 'unreadable' for a stored filed_path.

    Only a genuinely-absent file may be flagged failed; a stat that dies on
    permissions proves nothing about the file being gone, so it must never
    silently fail the row.
    """
    try:
        os.stat(path)
    # ruff 0.15.x with target-version=py314 rewrites `except (A, B):` to the
    # PEP 758 form; keep the parenthesized house style (see pdf/extract.py).
    except (FileNotFoundError, NotADirectoryError):  # fmt: skip
        return "missing"
    except OSError:
        return "unreadable"
    return "present"


def _plan(conn: sqlite3.Connection, archive_root: Path) -> _ReconcilePlan:
    rows = conn.execute("SELECT id, source_hash, filed_path, status FROM decisions").fetchall()
    # Symlinks are skipped: is_file() follows them, so a planted link could
    # otherwise index (and mis-attribute) content from outside archive_root.
    disk_pdfs = sorted(
        p
        for p in archive_root.rglob("*")
        if p.suffix.lower() == ".pdf" and not p.is_symlink() and p.is_file()
    )
    owners = _OwnerLookup.load(conn)
    row_state = {row["id"]: _row_state(row["filed_path"]) for row in rows}

    discovery = _classify_disk(rows, disk_pdfs, row_state, owners, archive_root)
    relinked_ids = {decision_id for decision_id, _, _ in discovery.relinks}

    orphan_ids = tuple(
        row["id"]
        for row in rows
        if row["id"] not in relinked_ids
        and row["status"] != DecisionStatus.FAILED.value
        and row_state[row["id"]] == "missing"
    )
    # A row flagged failed earlier whose file is back in place (restored
    # from backup, remounted, …) is stale — restore it to human_filed, the
    # same trust level as a discovered-on-disk file.
    recovered_ids = tuple(
        row["id"]
        for row in rows
        if row["id"] not in relinked_ids
        and row["status"] == DecisionStatus.FAILED.value
        and row_state[row["id"]] == "present"
    )
    in_sync = sum(
        1 for row in rows if row["id"] in relinked_ids or row_state[row["id"]] == "present"
    )
    unreadable_rows = tuple(
        row["filed_path"] for row in rows if row_state[row["id"]] == "unreadable"
    )
    return _ReconcilePlan(
        relinks=discovery.relinks,
        inserts=discovery.inserts,
        orphan_ids=orphan_ids,
        recovered_ids=recovered_ids,
        duplicates=discovery.duplicates,
        unreadable=discovery.unreadable + unreadable_rows,
        in_sync=in_sync,
        total_rows=len(rows),
    )


@dataclass(frozen=True, slots=True)
class _DiskDiscovery:
    """What the archive walk found that the decisions table doesn't know."""

    relinks: tuple[tuple[int, DecisionUpdate, bool], ...]  # (id, update, was failed)
    inserts: tuple[NewDecision, ...]
    duplicates: tuple[str, ...]
    unreadable: tuple[str, ...]


def _classify_disk(
    rows: list[sqlite3.Row],
    disk_pdfs: list[Path],
    row_state: dict[int, str],
    owners: _OwnerLookup,
    archive_root: Path,
) -> _DiskDiscovery:
    # Match stored rows to walked files by canonical spelling AND by
    # device/inode identity, never by raw string equality: on the macOS
    # deployment target's case-insensitive filesystem a case-only rename
    # changes the walked spelling while the stored row still points at the
    # same file, and a symlinked or otherwise non-canonical archive_root
    # changes every walked spelling at once.
    known_paths = {_canon(row["filed_path"]) for row in rows}
    known_files = {key for row in rows if (key := _file_key(row["filed_path"])) is not None}
    row_by_hash = {row["source_hash"]: row for row in rows}

    relinks: list[tuple[int, DecisionUpdate, bool]] = []
    relinked_ids: set[int] = set()
    inserts: list[NewDecision] = []
    planned_hashes: set[str] = set()
    duplicates: list[str] = []
    unreadable: list[str] = []

    for pdf in disk_pdfs:
        if _canon(pdf) in known_paths or _file_key(pdf) in known_files:
            continue
        try:
            source_hash = sha256_of_file(pdf)
        except OSError:
            # Unreadable or vanished mid-walk: one bad file must not abort
            # the whole reconcile — skip it and surface a warning.
            unreadable.append(str(pdf))
            continue
        existing = row_by_hash.get(source_hash)
        if existing is not None:
            # Relink only when the stored path is genuinely MISSING: an
            # 'unreadable' stat proves nothing about the file being gone
            # (same principle as failed-flagging), so re-pointing the row at
            # a same-content copy would clobber a possibly-present original.
            if row_state[existing["id"]] != "missing" or existing["id"] in relinked_ids:
                duplicates.append(str(pdf))
            else:
                was_failed = existing["status"] == DecisionStatus.FAILED.value
                relinks.append(
                    (
                        existing["id"],
                        _relink_update(owners, archive_root, pdf, was_failed),
                        was_failed,
                    )
                )
                relinked_ids.add(existing["id"])
        elif source_hash in planned_hashes:
            duplicates.append(str(pdf))
        else:
            planned_hashes.add(source_hash)
            inserts.append(_synthetic_decision(owners, archive_root, pdf, source_hash))

    return _DiskDiscovery(
        relinks=tuple(relinks),
        inserts=tuple(inserts),
        duplicates=tuple(duplicates),
        unreadable=tuple(unreadable),
    )


def _relink_update(
    owners: _OwnerLookup, archive_root: Path, pdf: Path, was_failed: bool
) -> DecisionUpdate:
    """The update for a row whose document was manually moved to `pdf`.

    Moving a file between archive folders is how the operator re-files it by
    hand (most importantly out of `_review/`), so the row follows the move:
    person/category are re-read from the new path when its segments resolve
    (never fallback-clobbered when they don't), and a document now filed
    under a real category leaves the review queue as human-filed.
    """
    person, category = _strict_owner(owners, archive_root, pdf)
    manually_filed = category is not None and not category.is_review
    moved_into_review = category is not None and category.is_review
    return DecisionUpdate(
        filed_path=str(pdf),
        person_id=person.id if person is not None else None,
        category_id=category.id if category is not None else None,
        # Out of _review = filed by hand; back INTO _review = the operator
        # wants it re-reviewed, so it must re-enter the review queue.
        needs_review=True if moved_into_review else (False if manually_filed else None),
        status=(
            DecisionStatus.REVIEW
            if moved_into_review
            else DecisionStatus.HUMAN_FILED
            if (manually_filed or was_failed)
            else None
        ),
    )


def _check_mass_flag(plan: _ReconcilePlan) -> None:
    # Guard denominator is ALL existing rows, deliberately including
    # already-failed ones — pinned by the story's acceptance criteria
    # ("more than 50% of existing decisions rows"), issue #4.
    if plan.total_rows and len(plan.orphan_ids) > plan.total_rows * _MASS_FLAG_THRESHOLD:
        raise ReconcileError(
            f"would flag {len(plan.orphan_ids)} of {plan.total_rows} decisions as failed "
            "(more than half) — likely a mis-mounted or half-synced archive; "
            "aborting without changes"
        )


def _apply(conn: sqlite3.Connection, plan: _ReconcilePlan) -> None:
    for decision_id, update, _ in plan.relinks:
        update_decision(conn, decision_id, update)
    for decision_id in plan.recovered_ids:
        update_decision(conn, decision_id, DecisionUpdate(status=DecisionStatus.HUMAN_FILED))
    for decision_id in plan.orphan_ids:
        update_decision(conn, decision_id, DecisionUpdate(status=DecisionStatus.FAILED))
    for decision in plan.inserts:
        insert_decision(conn, decision)


@dataclass(frozen=True, slots=True)
class _OwnerLookup:
    """Person/category slug lookups, loaded once so the per-PDF owner
    resolution never becomes N+1 queries on a large archive walk."""

    persons_by_slug: dict[str, PersonRow]
    categories_by_slug: dict[str, CategoryRow]
    review_category: CategoryRow | None

    @classmethod
    def load(cls, conn: sqlite3.Connection) -> _OwnerLookup:
        # include_inactive on BOTH lookups: reconcile honors the on-disk
        # layout, so a file physically under a deactivated person's or
        # category's folder keeps that folder's attribution. Keys are
        # lower-cased (as are lookups) because the macOS deployment
        # filesystem is case-insensitive: Timo/Rechnungen/ IS the timo
        # archive folder and must resolve to it.
        return cls(
            persons_by_slug={p.slug.lower(): p for p in list_persons(conn, include_inactive=True)},
            categories_by_slug={
                c.slug.lower(): c for c in list_categories(conn, include_inactive=True)
            },
            review_category=get_review_category(conn),
        )

    def fallback_person(self) -> PersonRow | None:
        if "shared" in self.persons_by_slug:
            return self.persons_by_slug["shared"]
        return min(self.persons_by_slug.values(), key=lambda p: p.id, default=None)


def _synthetic_decision(
    owners: _OwnerLookup, archive_root: Path, pdf: Path, source_hash: str
) -> NewDecision:
    person, category = _resolve_owner(owners, archive_root, pdf)
    return NewDecision(
        created_at=datetime.now(UTC),
        source_hash=source_hash,
        source_path=str(pdf),
        filed_path=str(pdf),
        person_id=person.id,
        category_id=category.id,
        doctype_id=None,
        document_date=None,
        counterparty=None,
        proposed_filename=pdf.name,
        overall_confidence=0.0,
        person_confidence=0.0,
        category_confidence=0.0,
        reasoning=DISCOVERED_REASONING,
        classifier_model="rebuild-index",
        new_category_proposal=None,
        needs_review=False,
        status=DecisionStatus.HUMAN_FILED,
    )


def _strict_owner(
    owners: _OwnerLookup, archive_root: Path, pdf: Path
) -> tuple[PersonRow | None, CategoryRow | None]:
    """Person + category read strictly from `<archive>/<person>/<category>/…`
    path segments — None for any segment that doesn't resolve, no fallbacks.

    The top-level `_review/` bucket has no person segment, so a first
    segment that isn't a person slug is tried as a category slug.
    """
    parts = pdf.relative_to(archive_root).parts
    person: PersonRow | None = None
    category: CategoryRow | None = None
    if len(parts) >= 2:
        person = owners.persons_by_slug.get(parts[0].lower())
        if person is not None and len(parts) >= 3:
            category = owners.categories_by_slug.get(parts[1].lower())
        elif person is None:
            category = owners.categories_by_slug.get(parts[0].lower())
    return person, category


def _resolve_owner(
    owners: _OwnerLookup, archive_root: Path, pdf: Path
) -> tuple[PersonRow, CategoryRow]:
    """Like :func:`_strict_owner`, but unresolvable segments fall back to
    the shared person / `_review` category — the same FK fallbacks the
    worker pipeline uses (manually dropped files can sit anywhere)."""
    person, category = _strict_owner(owners, archive_root, pdf)
    if person is None:
        person = owners.fallback_person()
    if person is None:
        raise ReconcileError("decisions need a person and the DB has none; run 'aido init' first")
    if category is None:
        category = owners.review_category
    if category is None:
        raise ReconcileError("DB has no _review category; run 'aido init' first")
    return person, category
