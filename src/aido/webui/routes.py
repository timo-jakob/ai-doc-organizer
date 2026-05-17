"""Feed routes: /, /needs-review, /all."""
from __future__ import annotations

from flask import Blueprint, current_app, render_template, abort, send_file

from aido.store.connection import connect
from aido.store.decisions import count_needs_review, list_recent, get_decision
from aido.store.persons import list_persons
from aido.store.taxonomy import list_categories

bp = Blueprint("feed", __name__)


def _state():
    return current_app.config["AIDO_STATE"]


@bp.route("/")
def index() -> str:
    state = _state()
    with connect(state.db_path) as conn:
        decisions = list_recent(conn, limit=50)
        pending = count_needs_review(conn)
        rows = _hydrate(conn, decisions)
    return render_template(
        "feed.html",
        decisions=rows,
        title="Recently filed",
        needs_review_count=pending,
        health=state.health.status.value,
    )


@bp.route("/needs-review")
def needs_review() -> str:
    state = _state()
    with connect(state.db_path) as conn:
        decisions = list_recent(conn, limit=200, needs_review_only=True)
        pending = count_needs_review(conn)
        rows = _hydrate(conn, decisions)
    return render_template(
        "feed.html",
        decisions=rows,
        title="Needs review",
        needs_review_count=pending,
        health=state.health.status.value,
    )


@bp.route("/all")
def all_decisions() -> str:
    state = _state()
    with connect(state.db_path) as conn:
        decisions = list_recent(conn, limit=500)
        pending = count_needs_review(conn)
        rows = _hydrate(conn, decisions)
    return render_template(
        "feed.html",
        decisions=rows,
        title="All decisions",
        needs_review_count=pending,
        health=state.health.status.value,
    )


def _hydrate(conn, decisions):
    """Attach person and category slug to each row for display."""
    out = []
    for d in decisions:
        person = conn.execute(
            "SELECT slug, display_name FROM persons WHERE id = ?", (d.person_id,)
        ).fetchone()
        cat = conn.execute(
            "SELECT slug, display_name FROM categories WHERE id = ?", (d.category_id,)
        ).fetchone()
        out.append({
            "decision": d,
            "person_slug": person["slug"] if person else "?",
            "person_display": person["display_name"] if person else "?",
            "category_slug": cat["slug"] if cat else "?",
            "category_display": cat["display_name"] if cat else "?",
        })
    return out


@bp.route("/decisions/<int:decision_id>")
def detail(decision_id: int) -> str:
    state = _state()
    with connect(state.db_path) as conn:
        d = get_decision(conn, decision_id)
        if d is None:
            abort(404)
        pending = count_needs_review(conn)
        person = conn.execute(
            "SELECT slug, display_name FROM persons WHERE id = ?", (d.person_id,)
        ).fetchone()
        cat = conn.execute(
            "SELECT slug, display_name FROM categories WHERE id = ?", (d.category_id,)
        ).fetchone()
        all_persons = list_persons(conn)
        all_categories = list_categories(conn)
    return render_template(
        "detail.html",
        decision=d,
        person_slug=person["slug"] if person else "?",
        category_slug=cat["slug"] if cat else "?",
        all_persons=all_persons,
        all_categories=all_categories,
        needs_review_count=pending,
        health=state.health.status.value,
    )


@bp.route("/pdf/<int:decision_id>")
def pdf(decision_id: int):
    state = _state()
    with connect(state.db_path) as conn:
        d = get_decision(conn, decision_id)
    if d is None:
        abort(404)
    from pathlib import Path
    p = Path(d.filed_path)
    if not p.exists():
        abort(404)
    return send_file(p, mimetype="application/pdf")


@bp.route("/stats")
def stats() -> str:
    state = _state()
    with connect(state.db_path) as conn:
        pending = count_needs_review(conn)
        total = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        last7 = conn.execute(
            "SELECT COUNT(*) FROM decisions WHERE created_at >= datetime('now', '-7 days')"
        ).fetchone()[0]
        avg_conf = conn.execute(
            "SELECT AVG(overall_confidence) FROM decisions WHERE status = 'auto_filed'"
        ).fetchone()[0]
    return render_template(
        "stats.html",
        total=total,
        last7=last7,
        avg_confidence=avg_conf or 0.0,
        needs_review_count=pending,
        health=state.health.status.value,
    )
