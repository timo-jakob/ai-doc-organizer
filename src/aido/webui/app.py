"""Flask app factory for the retro-audit web UI."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from flask import Flask, jsonify, render_template

from aido.daemon import HealthState
from aido.mutations import MutationContext
from aido.store.connection import connect
from aido.store.decisions import count_needs_review


@dataclass
class WebState:
    db_path: Path
    archive_root: Path
    mutations: MutationContext
    health: HealthState


def create_app(state: WebState) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["AIDO_STATE"] = state

    @app.route("/")
    def index() -> str:
        # Real feed is implemented in Task 26; for now show the shell.
        with connect(state.db_path) as conn:
            pending = count_needs_review(conn)
        return render_template("base.html", needs_review_count=pending,
                               health=state.health.status.value)

    @app.route("/healthz")
    def healthz():
        with connect(state.db_path) as conn:
            pending = count_needs_review(conn)
        return jsonify(
            {
                "status": state.health.status.value,
                "needs_review": pending,
                "last_classification_at": (
                    state.health.last_classification_at.isoformat()
                    if state.health.last_classification_at
                    else None
                ),
            }
        )

    return app
