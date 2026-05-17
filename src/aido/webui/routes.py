"""Feed routes: /, /needs-review, /all."""
from __future__ import annotations

from flask import Blueprint, current_app, render_template

from aido.store.connection import connect
from aido.store.decisions import count_needs_review, list_recent

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
