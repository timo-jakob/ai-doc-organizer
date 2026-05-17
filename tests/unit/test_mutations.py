import threading
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from aido.mutations import (
    MutationContext,
    approve,
    delete_decision,
    promote_category,
    re_file,
    rename,
)
from aido.store.connection import connect
from aido.store.decisions import NewDecision, get_decision, insert_decision
from aido.store.manual_actions import list_actions_for_decision
from aido.store.migrations import init_db
from aido.store.persons import create_person
from aido.store.taxonomy import (
    create_category,
    create_doctype,
    get_category_by_slug,
)
from aido.types import DecisionStatus, ManualAction


@pytest.fixture
def ctx(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    with connect(tmp_path / "x.sqlite") as conn:
        init_db(conn)
        p_timo = create_person(conn, slug="timo", display_name="Timo")
        p_anna = create_person(conn, slug="anna", display_name="Anna")
        cat_re = create_category(conn, slug="rechnungen", display_name="Rechnungen")
        cat_st = create_category(conn, slug="steuer", display_name="Steuer")
        cat_rv = create_category(conn, slug="_review", display_name="_review", is_review=True)
        dt = create_doctype(conn, slug="rechnung", display_name="Rechnung")
        # Place a real file at the filed_path so re_file can move it.
        filed = archive / "timo" / "rechnungen" / "2026-03-12_rechnung_telekom.pdf"
        filed.parent.mkdir(parents=True)
        filed.write_bytes(b"pdf-bytes")
        new_id = insert_decision(
            conn,
            NewDecision(
                created_at=datetime(2026, 5, 17, 10, tzinfo=timezone.utc),
                source_hash="h1",
                source_path="/scans/scan001.pdf",
                filed_path=str(filed),
                person_id=p_timo.id,
                category_id=cat_re.id,
                doctype_id=dt.id,
                document_date=date(2026, 3, 12),
                counterparty="telekom",
                proposed_filename="2026-03-12_rechnung_telekom.pdf",
                overall_confidence=0.93,
                person_confidence=0.95,
                category_confidence=0.91,
                reasoning="x",
                classifier_model="claude-opus-4-7",
                new_category_proposal=None,
                needs_review=False,
                status=DecisionStatus.AUTO_FILED,
            ),
        )
        mctx = MutationContext(conn=conn, archive_root=archive, lock=threading.Lock(),
                               now=lambda: datetime(2026, 5, 17, 11, tzinfo=timezone.utc))
        yield {
            "ctx": mctx,
            "decision_id": new_id,
            "timo": p_timo,
            "anna": p_anna,
            "rechnungen": cat_re,
            "steuer": cat_st,
            "review": cat_rv,
        }


def test_re_file_moves_file_and_updates_decision(ctx):
    out = re_file(
        ctx["ctx"],
        ctx["decision_id"],
        person_id=ctx["anna"].id,
        category_id=ctx["steuer"].id,
        filename="2026-03-12_rechnung_telekom.pdf",
    )
    assert out.exists()
    assert out.parent.name == "steuer"
    assert out.parent.parent.name == "anna"
    d = get_decision(ctx["ctx"].conn, ctx["decision_id"])
    assert d.filed_path == str(out)
    assert d.person_id == ctx["anna"].id
    assert d.category_id == ctx["steuer"].id
    assert d.status == DecisionStatus.HUMAN_FILED
    [audit] = list_actions_for_decision(ctx["ctx"].conn, ctx["decision_id"])
    assert audit.action == ManualAction.RE_FILE


def test_rename_renames_in_place(ctx):
    out = rename(ctx["ctx"], ctx["decision_id"], filename="2026-03-12_rechnung_telekom-2.pdf")
    assert out.exists()
    assert out.name == "2026-03-12_rechnung_telekom-2.pdf"
    [audit] = list_actions_for_decision(ctx["ctx"].conn, ctx["decision_id"])
    assert audit.action == ManualAction.RENAME


def test_delete_removes_file_and_logs(ctx):
    delete_decision(ctx["ctx"], ctx["decision_id"], note="duplicate")
    d = get_decision(ctx["ctx"].conn, ctx["decision_id"])
    assert d.status == DecisionStatus.FAILED  # treated as 'no longer in archive'
    assert not Path(d.filed_path).exists()
    [audit] = list_actions_for_decision(ctx["ctx"].conn, ctx["decision_id"])
    assert audit.action == ManualAction.DELETE
    assert audit.note == "duplicate"


def test_approve_logs_and_marks_not_needs_review(ctx):
    # Flip the decision into needs_review first.
    ctx["ctx"].conn.execute(
        "UPDATE decisions SET needs_review = 1, status = ? WHERE id = ?",
        (DecisionStatus.REVIEW.value, ctx["decision_id"]),
    )
    approve(ctx["ctx"], ctx["decision_id"])
    d = get_decision(ctx["ctx"].conn, ctx["decision_id"])
    assert d.needs_review is False
    assert d.status == DecisionStatus.AUTO_FILED  # 'approve' means keep AI choice
    [audit] = list_actions_for_decision(ctx["ctx"].conn, ctx["decision_id"])
    assert audit.action == ManualAction.APPROVE


def test_promote_category_creates_category_and_refiles(ctx):
    new_cat = promote_category(
        ctx["ctx"],
        ctx["decision_id"],
        new_category_slug="garten",
        new_category_display_name="Garten",
        person_id=ctx["timo"].id,
        filename="2026-03-12_rechnung_telekom.pdf",
    )
    assert new_cat.slug == "garten"
    assert get_category_by_slug(ctx["ctx"].conn, "garten") is not None
    d = get_decision(ctx["ctx"].conn, ctx["decision_id"])
    assert d.category_id == new_cat.id
    assert Path(d.filed_path).parent.name == "garten"
    [audit] = list_actions_for_decision(ctx["ctx"].conn, ctx["decision_id"])
    assert audit.action == ManualAction.PROMOTE_CATEGORY
