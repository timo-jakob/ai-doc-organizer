"""POST endpoints that call into aido.mutations under the daemon's lock."""
from __future__ import annotations

from flask import Blueprint, abort, current_app, jsonify, request

from aido.mutations import (
    MutationContext,
    approve,
    delete_decision,
    promote_category,
    re_file,
    rename,
)
from aido.store.persons import get_person_by_slug
from aido.store.taxonomy import get_category_by_slug

bp = Blueprint("mutations", __name__)


def _ctx() -> MutationContext:
    return current_app.config["AIDO_STATE"].mutations


def _resolve_person_id(slug: str) -> int:
    person = get_person_by_slug(_ctx().conn, slug)
    if person is None:
        abort(400, description=f"Unknown person slug: {slug}")
    return person.id


def _resolve_category_id(slug: str) -> int:
    cat = get_category_by_slug(_ctx().conn, slug)
    if cat is None:
        abort(400, description=f"Unknown category slug: {slug}")
    return cat.id


@bp.post("/decisions/<int:decision_id>/re-file")
def post_refile(decision_id: int):
    body = request.get_json(force=True) or {}
    try:
        re_file(
            _ctx(),
            decision_id,
            person_id=_resolve_person_id(body["person_slug"]),
            category_id=_resolve_category_id(body["category_slug"]),
            filename=body["filename"],
            note=body.get("note"),
        )
    except ValueError as e:
        if "Unknown decision" in str(e):
            abort(404)
        abort(400, description=str(e))
    return jsonify({"ok": True})


@bp.post("/decisions/<int:decision_id>/rename")
def post_rename(decision_id: int):
    body = request.get_json(force=True) or {}
    try:
        rename(_ctx(), decision_id, filename=body["filename"], note=body.get("note"))
    except ValueError as e:
        if "Unknown decision" in str(e):
            abort(404)
        abort(400, description=str(e))
    return jsonify({"ok": True})


@bp.post("/decisions/<int:decision_id>/delete")
def post_delete(decision_id: int):
    body = request.get_json(silent=True) or {}
    try:
        delete_decision(_ctx(), decision_id, note=body.get("note"))
    except ValueError as e:
        if "Unknown decision" in str(e):
            abort(404)
        abort(400, description=str(e))
    return jsonify({"ok": True})


@bp.post("/decisions/<int:decision_id>/approve")
def post_approve(decision_id: int):
    body = request.get_json(silent=True) or {}
    try:
        approve(_ctx(), decision_id, note=body.get("note"))
    except ValueError as e:
        if "Unknown decision" in str(e):
            abort(404)
        abort(400, description=str(e))
    return jsonify({"ok": True})


@bp.post("/decisions/<int:decision_id>/promote-category")
def post_promote(decision_id: int):
    body = request.get_json(force=True) or {}
    try:
        promote_category(
            _ctx(),
            decision_id,
            new_category_slug=body["new_category_slug"],
            new_category_display_name=body["new_category_display_name"],
            person_id=_resolve_person_id(body["person_slug"]),
            filename=body["filename"],
            note=body.get("note"),
        )
    except ValueError as e:
        if "Unknown decision" in str(e):
            abort(404)
        abort(400, description=str(e))
    return jsonify({"ok": True})
