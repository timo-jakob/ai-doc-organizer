"""Single-writer mutation API used by both the worker thread and the web UI.

Each function acquires `MutationContext.lock` for the duration of the call so
that worker pipeline writes and HTTP-driven writes cannot race. All mutations
write to `manual_actions` as part of the same transaction.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from aido.filing.executor import FilingTarget, file_document
from aido.filing.filename import next_available_name
from aido.store.decisions import DecisionUpdate, get_decision, update_decision
from aido.store.manual_actions import NewManualAction, insert_manual_action
from aido.store.taxonomy import (
    CategoryRow,
    create_category,
    get_category_by_slug,
)
from aido.types import DecisionStatus, ManualAction


@dataclass(frozen=True, slots=True)
class MutationContext:
    conn: sqlite3.Connection
    archive_root: Path
    lock: threading.Lock
    now: Callable[[], datetime]


def _person_slug_or_none(ctx: MutationContext, person_id: int | None) -> str | None:
    if person_id is None:
        return None
    row = ctx.conn.execute(
        "SELECT slug, is_shared FROM persons WHERE id = ?", (person_id,)
    ).fetchone()
    if row is None:
        return None
    return row["slug"]


def _category_slug(ctx: MutationContext, category_id: int) -> str:
    row = ctx.conn.execute(
        "SELECT slug FROM categories WHERE id = ?", (category_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Unknown category id {category_id}")
    return row["slug"]


def re_file(
    ctx: MutationContext,
    decision_id: int,
    *,
    person_id: int,
    category_id: int,
    filename: str,
    note: str | None = None,
) -> Path:
    """Move the filed document to a new person/category, optionally renaming."""
    with ctx.lock:
        d = get_decision(ctx.conn, decision_id)
        if d is None:
            raise ValueError(f"Unknown decision id {decision_id}")
        src = Path(d.filed_path)
        if not src.exists():
            raise FileNotFoundError(f"Filed PDF missing: {src}")
        person_slug = _person_slug_or_none(ctx, person_id)
        cat_slug = _category_slug(ctx, category_id)
        dest = file_document(
            src,
            archive_root=ctx.archive_root,
            target=FilingTarget(
                person_slug=person_slug,
                category_slug=cat_slug,
                filename=filename,
            ),
        )
        with ctx.conn:
            update_decision(
                ctx.conn,
                decision_id,
                DecisionUpdate(
                    filed_path=str(dest),
                    person_id=person_id,
                    category_id=category_id,
                    proposed_filename=filename,
                    needs_review=False,
                    status=DecisionStatus.HUMAN_FILED,
                ),
            )
            insert_manual_action(
                ctx.conn,
                NewManualAction(
                    decision_id=decision_id,
                    action=ManualAction.RE_FILE,
                    before_path=str(src),
                    after_path=str(dest),
                    before_person_id=d.person_id,
                    after_person_id=person_id,
                    before_category_id=d.category_id,
                    after_category_id=category_id,
                    created_at=ctx.now(),
                    note=note,
                ),
            )
        return dest


def rename(
    ctx: MutationContext, decision_id: int, *, filename: str, note: str | None = None
) -> Path:
    """Rename the filed document in place."""
    with ctx.lock:
        d = get_decision(ctx.conn, decision_id)
        if d is None:
            raise ValueError(f"Unknown decision id {decision_id}")
        src = Path(d.filed_path)
        if not src.exists():
            raise FileNotFoundError(f"Filed PDF missing: {src}")
        dest = next_available_name(src.parent / filename)
        os.replace(src, dest)
        with ctx.conn:
            update_decision(
                ctx.conn,
                decision_id,
                DecisionUpdate(filed_path=str(dest), proposed_filename=filename),
            )
            insert_manual_action(
                ctx.conn,
                NewManualAction(
                    decision_id=decision_id,
                    action=ManualAction.RENAME,
                    before_path=str(src),
                    after_path=str(dest),
                    before_person_id=d.person_id,
                    after_person_id=d.person_id,
                    before_category_id=d.category_id,
                    after_category_id=d.category_id,
                    created_at=ctx.now(),
                    note=note,
                ),
            )
        return dest


def delete_decision(
    ctx: MutationContext, decision_id: int, *, note: str | None = None
) -> None:
    """Remove the filed PDF from disk and mark the decision FAILED."""
    with ctx.lock:
        d = get_decision(ctx.conn, decision_id)
        if d is None:
            raise ValueError(f"Unknown decision id {decision_id}")
        src = Path(d.filed_path)
        if src.exists():
            src.unlink()
        with ctx.conn:
            update_decision(
                ctx.conn,
                decision_id,
                DecisionUpdate(status=DecisionStatus.FAILED, needs_review=False),
            )
            insert_manual_action(
                ctx.conn,
                NewManualAction(
                    decision_id=decision_id,
                    action=ManualAction.DELETE,
                    before_path=str(src),
                    after_path=None,
                    before_person_id=d.person_id,
                    after_person_id=None,
                    before_category_id=d.category_id,
                    after_category_id=None,
                    created_at=ctx.now(),
                    note=note,
                ),
            )


def approve(
    ctx: MutationContext, decision_id: int, *, note: str | None = None
) -> None:
    """Accept the classifier's decision: clear `needs_review`, mark AUTO_FILED."""
    with ctx.lock:
        d = get_decision(ctx.conn, decision_id)
        if d is None:
            raise ValueError(f"Unknown decision id {decision_id}")
        with ctx.conn:
            update_decision(
                ctx.conn,
                decision_id,
                DecisionUpdate(
                    needs_review=False,
                    status=DecisionStatus.AUTO_FILED,
                ),
            )
            insert_manual_action(
                ctx.conn,
                NewManualAction(
                    decision_id=decision_id,
                    action=ManualAction.APPROVE,
                    before_path=d.filed_path,
                    after_path=d.filed_path,
                    before_person_id=d.person_id,
                    after_person_id=d.person_id,
                    before_category_id=d.category_id,
                    after_category_id=d.category_id,
                    created_at=ctx.now(),
                    note=note,
                ),
            )


def promote_category(
    ctx: MutationContext,
    decision_id: int,
    *,
    new_category_slug: str,
    new_category_display_name: str,
    person_id: int,
    filename: str,
    note: str | None = None,
) -> CategoryRow:
    """Create a new category from a proposal, then re-file the document into it."""
    with ctx.lock:
        d = get_decision(ctx.conn, decision_id)
        if d is None:
            raise ValueError(f"Unknown decision id {decision_id}")
        existing = get_category_by_slug(ctx.conn, new_category_slug)
        if existing is not None:
            new_cat = existing
        else:
            with ctx.conn:
                new_cat = create_category(
                    ctx.conn,
                    slug=new_category_slug,
                    display_name=new_category_display_name,
                )

        src = Path(d.filed_path)
        if not src.exists():
            raise FileNotFoundError(f"Filed PDF missing: {src}")
        person_slug = _person_slug_or_none(ctx, person_id)
        dest = file_document(
            src,
            archive_root=ctx.archive_root,
            target=FilingTarget(
                person_slug=person_slug,
                category_slug=new_cat.slug,
                filename=filename,
            ),
        )
        with ctx.conn:
            update_decision(
                ctx.conn,
                decision_id,
                DecisionUpdate(
                    filed_path=str(dest),
                    person_id=person_id,
                    category_id=new_cat.id,
                    proposed_filename=filename,
                    needs_review=False,
                    status=DecisionStatus.HUMAN_FILED,
                ),
            )
            insert_manual_action(
                ctx.conn,
                NewManualAction(
                    decision_id=decision_id,
                    action=ManualAction.PROMOTE_CATEGORY,
                    before_path=str(src),
                    after_path=str(dest),
                    before_person_id=d.person_id,
                    after_person_id=person_id,
                    before_category_id=d.category_id,
                    after_category_id=new_cat.id,
                    created_at=ctx.now(),
                    note=note,
                ),
            )
        return new_cat
