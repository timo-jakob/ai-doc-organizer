"""Settings page: list and admin persons/aliases/categories/doctypes."""

from __future__ import annotations

import sqlite3

from flask import Blueprint, abort, current_app, jsonify, render_template, request

from aido.store.connection import connect
from aido.store.decisions import count_needs_review
from aido.store.persons import (
    add_alias,
    create_person,
    get_person_by_slug,
    list_aliases_for,
    list_persons,
)
from aido.store.taxonomy import (
    create_category,
    create_doctype,
    get_category_by_slug,
    get_doctype_by_slug,
    list_categories,
    list_doctypes,
)

bp = Blueprint("settings", __name__)


def _state():
    return current_app.config["AIDO_STATE"]


@bp.route("/settings", methods=["GET"])
def settings_page() -> str:
    state = _state()
    with connect(state.db_path) as conn:
        persons = list_persons(conn, include_inactive=True)
        aliases_by_person = {p.id: list_aliases_for(conn, p.id) for p in persons}
        cats = list_categories(conn, include_inactive=True)
        doctypes = list_doctypes(conn, include_inactive=True)
        pending = count_needs_review(conn)
    return render_template(
        "settings.html",
        persons=persons,
        aliases_by_person=aliases_by_person,
        categories=cats,
        doctypes=doctypes,
        needs_review_count=pending,
        health=state.health.status.value,
    )


def _conn() -> sqlite3.Connection:
    return _state().mutations.conn


@bp.post("/settings/persons")
def add_person_route():
    body = request.get_json(force=True) or {}
    slug = body["slug"]
    with _state().mutations.lock:
        if get_person_by_slug(_conn(), slug) is not None:
            abort(400, description=f"Person slug {slug!r} already exists")
        with _conn():
            person = create_person(
                _conn(),
                slug=slug,
                display_name=body["display_name"],
                is_shared=bool(body.get("is_shared", False)),
            )
            for alias in body.get("aliases") or []:
                add_alias(_conn(), person_id=person.id, alias=alias)
    return jsonify({"ok": True, "id": person.id})


@bp.post("/settings/persons/<int:person_id>/aliases")
def add_alias_route(person_id: int):
    body = request.get_json(force=True) or {}
    try:
        with _state().mutations.lock, _conn():
            row = add_alias(_conn(), person_id=person_id, alias=body["alias"])
    except sqlite3.IntegrityError as e:
        abort(400, description=str(e))
    return jsonify({"ok": True, "id": row.id})


@bp.post("/settings/categories")
def add_category_route():
    body = request.get_json(force=True) or {}
    slug = body["slug"]
    with _state().mutations.lock:
        if get_category_by_slug(_conn(), slug) is not None:
            abort(400, description=f"Category slug {slug!r} already exists")
        with _conn():
            cat = create_category(
                _conn(),
                slug=slug,
                display_name=body["display_name"],
                description=body.get("description"),
            )
    return jsonify({"ok": True, "id": cat.id})


@bp.post("/settings/doctypes")
def add_doctype_route():
    body = request.get_json(force=True) or {}
    slug = body["slug"]
    with _state().mutations.lock:
        if get_doctype_by_slug(_conn(), slug) is not None:
            abort(400, description=f"Doctype slug {slug!r} already exists")
        with _conn():
            dt = create_doctype(
                _conn(),
                slug=slug,
                display_name=body["display_name"],
                description=body.get("description"),
            )
    return jsonify({"ok": True, "id": dt.id})
