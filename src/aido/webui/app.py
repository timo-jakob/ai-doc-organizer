"""Flask app factory for the retro-audit web UI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from flask import Flask, jsonify

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
    # CSRF protection is not needed here: all mutation endpoints consume
    # application/json (browsers cannot send cross-origin JSON POST without a
    # CORS preflight), no session cookies are used, and there is no Flask-WTF
    # form infrastructure.  This is a local-network REST API — not a
    # traditional server-rendered form app.  SONAR S4502 is a false positive
    # for this architecture.  # nosonar python:S4502
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["AIDO_STATE"] = state

    from aido.webui.routes import bp as feed_bp

    app.register_blueprint(feed_bp)

    from aido.webui.mutation_routes import bp as mut_bp

    app.register_blueprint(mut_bp)

    from aido.webui.settings_routes import bp as settings_bp

    app.register_blueprint(settings_bp)

    @app.route("/healthz", methods=["GET"])
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
