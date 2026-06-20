"""aido command-line interface.

Subcommands:
- init: bootstrap the DB (persons, aliases, categories, doctypes).
- status: print health + counts.
- rebuild-index: scan the archive directory and reconcile decisions table.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from ruamel.yaml import YAML

from aido.store.connection import connect
from aido.store.migrations import init_db
from aido.store.persons import add_alias, create_person, get_person_by_slug
from aido.store.taxonomy import (
    create_category,
    create_doctype,
    get_category_by_slug,
    get_doctype_by_slug,
)

_DEFAULT_CATEGORIES = [
    ("rechnungen", "Rechnungen", "Eingehende Rechnungen aller Art"),
    ("steuer", "Steuer", "Steuerbescheide, Steuererklärungen, Schreiben vom Finanzamt"),
    ("medizin", "Medizin", "Arztbriefe, Befunde, Rezepte"),
    ("vertraege", "Verträge", "Verträge und Vertragsänderungen"),
    ("bank", "Bank", "Kontoauszüge, Bankschreiben"),
    ("versicherung", "Versicherung", "Policen, Schadensmeldungen"),
    ("nebenkosten", "Nebenkosten", "Strom, Wasser, Gas, Müll"),
    ("briefe", "Briefe", "Allgemeine Korrespondenz"),
    ("schule", "Schule", "Zeugnisse, Elternbriefe, Schultermine"),
]

_DEFAULT_DOCTYPES = [
    ("rechnung", "Rechnung", "Eine Rechnung von einem Anbieter"),
    ("steuerbescheid", "Steuerbescheid", "Bescheid vom Finanzamt"),
    ("kontoauszug", "Kontoauszug", "Bank-Kontoauszug"),
    ("vertrag", "Vertrag", "Vertragsdokument"),
    ("versicherungs-schreiben", "Versicherungsschreiben", "Schreiben einer Versicherung"),
    ("arztbrief", "Arztbrief", "Schreiben eines Arztes oder Krankenhauses"),
    ("zeugnis", "Zeugnis", "Schulzeugnis"),
    ("letter", "Brief", "Allgemeines Schreiben (Fallback)"),
]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aido")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="bootstrap the DB and archive folders")
    p_init.add_argument("--db", type=Path, required=True)
    p_init.add_argument("--seed", type=Path, help="YAML seed file (non-interactive)")
    p_init.add_argument("--archive-root", type=Path, help="create this directory if missing")
    p_init.add_argument("--scan-inbox", type=Path, help="create this directory if missing")

    p_status = sub.add_parser("status", help="print health and queue counts")
    p_status.add_argument("--db", type=Path, required=True)

    p_reindex = sub.add_parser(
        "rebuild-index",
        help="scan the archive and reconcile (no-op placeholder for v1)",
    )
    p_reindex.add_argument("--db", type=Path, required=True)

    args = parser.parse_args(argv)

    if args.cmd == "init":
        return _cmd_init(args)
    if args.cmd == "status":
        return _cmd_status(args)
    if args.cmd == "rebuild-index":
        # v1: keep a no-op stub; real reconciliation lands in a follow-up.
        print("rebuild-index: no-op placeholder for v1", file=sys.stderr)
        return 0
    parser.error(f"unknown command: {args.cmd}")
    return 2  # unreachable


def _cmd_init(args: argparse.Namespace) -> int:
    if args.archive_root is not None:
        args.archive_root.mkdir(
            parents=True, exist_ok=True
        )  # nosonar pythonsecurity:S8707 — path is an argparse argument supplied by the human operator, not derived from LLM output
    if args.scan_inbox is not None:
        args.scan_inbox.mkdir(
            parents=True, exist_ok=True
        )  # nosonar pythonsecurity:S8707 — path is an argparse argument supplied by the human operator, not derived from LLM output

    with connect(args.db) as conn:
        init_db(conn)
        if args.seed is not None:
            _seed_from_yaml(conn, args.seed)
        else:
            _seed_interactive(conn)
        # Ensure the _review category always exists.
        if get_category_by_slug(conn, "_review") is None:
            with conn:
                create_category(conn, slug="_review", display_name="_review", is_review=True)
        # Apply defaults for any missing categories/doctypes (no overwrite).
        with conn:
            for slug, name, desc in _DEFAULT_CATEGORIES:
                if get_category_by_slug(conn, slug) is None:
                    create_category(conn, slug=slug, display_name=name, description=desc)
            for slug, name, desc in _DEFAULT_DOCTYPES:
                if get_doctype_by_slug(conn, slug) is None:
                    create_doctype(conn, slug=slug, display_name=name, description=desc)
    print(f"init: db ready at {args.db}")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    from aido.store.decisions import count_needs_review

    with connect(args.db) as conn:
        n = count_needs_review(conn)
    print(f"needs_review: {n}")
    return 0


def _seed_person(conn, entry: dict) -> None:
    """Create one person and their aliases if the slug does not yet exist."""
    slug = entry["slug"]
    if get_person_by_slug(conn, slug) is not None:
        return
    person = create_person(
        conn,
        slug=slug,
        display_name=entry["display_name"],
        is_shared=bool(entry.get("is_shared", False)),
    )
    for alias in entry.get("aliases", []) or []:
        add_alias(conn, person_id=person.id, alias=alias)


def _seed_from_yaml(conn, seed_path: Path) -> None:
    yaml = YAML(typ="safe")
    data = (
        yaml.load(seed_path.read_text(encoding="utf-8")) or {}
    )  # nosonar pythonsecurity:S8707 — seed_path is an argparse argument supplied by the human operator, not derived from LLM output
    with conn:
        for entry in data.get("persons", []) or []:
            _seed_person(conn, entry)
        for entry in data.get("categories", []) or []:
            slug = entry["slug"]
            if get_category_by_slug(conn, slug) is None:
                create_category(
                    conn,
                    slug=slug,
                    display_name=entry["display_name"],
                    description=entry.get("description"),
                    is_review=bool(entry.get("is_review", False)),
                )
        for entry in data.get("doctypes", []) or []:
            slug = entry["slug"]
            if get_doctype_by_slug(conn, slug) is None:
                create_doctype(
                    conn,
                    slug=slug,
                    display_name=entry["display_name"],
                    description=entry.get("description"),
                )


def _seed_interactive(conn) -> None:
    print(
        "Interactive init: configure four family members + a shared bucket.\n"
        "You can run this again later, or use --seed seed.yaml for non-interactive setup."
    )
    with conn:
        for i in range(1, 5):
            slug = input(f"Person {i} slug (e.g. 'timo'): ").strip()
            if not slug:
                continue
            if get_person_by_slug(conn, slug) is not None:
                print(f"  skipping {slug} (already exists)")
                continue
            display = input(f"  Display name for {slug}: ").strip() or slug
            person = create_person(conn, slug=slug, display_name=display)
            raw_aliases = input(f"  Aliases for {slug} (comma-separated): ").strip()
            for alias in (a.strip() for a in raw_aliases.split(",") if a.strip()):
                add_alias(conn, person_id=person.id, alias=alias)
        if get_person_by_slug(conn, "shared") is None:
            create_person(conn, slug="shared", display_name="Shared", is_shared=True)
            print("  added shared bucket")


if __name__ == "__main__":
    sys.exit(main())
