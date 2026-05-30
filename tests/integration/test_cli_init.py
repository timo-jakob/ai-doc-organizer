from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from aido.cli import main as cli_main
from aido.store.connection import connect
from aido.store.decisions import NewDecision, insert_decision
from aido.store.migrations import init_db
from aido.store.persons import (
    create_person,
    find_person_by_alias,
    get_person_by_slug,
    list_aliases_for,
    list_persons,
)
from aido.store.taxonomy import (
    create_category,
    create_doctype,
    get_doctype_by_slug,
    get_review_category,
    list_categories,
)
from aido.types import DecisionStatus


def test_init_with_seed_file(tmp_path: Path):
    db = tmp_path / "aido.sqlite"
    seed = tmp_path / "seed.yaml"
    seed.write_text(
        """
persons:
  - slug: timo
    display_name: Timo Jakob
    aliases: [Timo Jakob, T. Jakob, Jakob]
  - slug: anna
    display_name: Anna Jakob
    aliases: [Anna Jakob]
  - slug: penelope
    display_name: Pénélope Müller
    aliases: [Penelope, Penélope, Müller]
  - slug: child2
    display_name: Lea Jakob
    aliases: [Lea Jakob]
  - slug: shared
    display_name: Shared
    is_shared: true
    aliases: []

categories:
  - slug: rechnungen
    display_name: Rechnungen
  - slug: steuer
    display_name: Steuer
  - slug: medizin
    display_name: Medizin
  - slug: vertraege
    display_name: Verträge

doctypes:
  - slug: rechnung
    display_name: Rechnung
  - slug: letter
    display_name: Brief
""".strip(),
        encoding="utf-8",
    )
    rc = cli_main(["init", "--db", str(db), "--seed", str(seed)])
    assert rc == 0
    with connect(db) as conn:
        slugs = {p.slug for p in list_persons(conn)}
        assert slugs == {"timo", "anna", "penelope", "child2", "shared"}
        # Aliases were inserted and are case/accent-insensitive.
        assert find_person_by_alias(conn, "penelope") is not None
        assert find_person_by_alias(conn, "Penélope") is not None
        # Categories include the user's list + the _review row that init adds automatically.
        cat_slugs = {c.slug for c in list_categories(conn, include_inactive=True)}
        assert "_review" in cat_slugs
        assert {"rechnungen", "steuer", "medizin", "vertraege"} <= cat_slugs
        assert get_review_category(conn) is not None
        assert get_doctype_by_slug(conn, "rechnung") is not None


def test_init_is_idempotent(tmp_path: Path):
    db = tmp_path / "aido.sqlite"
    seed = tmp_path / "seed.yaml"
    seed.write_text(
        """
persons:
  - slug: timo
    display_name: Timo
    aliases: [Timo]
categories: []
doctypes: []
""".strip(),
        encoding="utf-8",
    )
    rc1 = cli_main(["init", "--db", str(db), "--seed", str(seed)])
    rc2 = cli_main(["init", "--db", str(db), "--seed", str(seed)])
    assert rc1 == 0 and rc2 == 0  # second run must not raise
    with connect(db) as conn:
        slugs = [p.slug for p in list_persons(conn)]
        assert slugs == ["timo"]  # not duplicated


def test_init_creates_archive_and_inbox_paths(tmp_path: Path, monkeypatch):
    db = tmp_path / "aido.sqlite"
    archive = tmp_path / "archive"
    inbox = tmp_path / "inbox"
    seed = tmp_path / "seed.yaml"
    seed.write_text("persons: []\ncategories: []\ndoctypes: []\n", encoding="utf-8")
    rc = cli_main(
        [
            "init",
            "--db",
            str(db),
            "--seed",
            str(seed),
            "--archive-root",
            str(archive),
            "--scan-inbox",
            str(inbox),
        ]
    )
    assert rc == 0
    assert archive.exists()
    assert inbox.exists()


def test_init_applies_default_categories_and_doctypes(tmp_path: Path):
    """A seed file that omits categories/doctypes still gets the built-in defaults."""
    db = tmp_path / "aido.sqlite"
    seed = tmp_path / "seed.yaml"
    seed.write_text("persons: []\ncategories: []\ndoctypes: []\n", encoding="utf-8")
    rc = cli_main(["init", "--db", str(db), "--seed", str(seed)])
    assert rc == 0
    with connect(db) as conn:
        cat_slugs = {c.slug for c in list_categories(conn, include_inactive=True)}
        # _DEFAULT_CATEGORIES from aido.cli must all be present.
        assert {
            "rechnungen",
            "steuer",
            "medizin",
            "vertraege",
            "bank",
            "versicherung",
            "nebenkosten",
            "briefe",
            "schule",
        } <= cat_slugs
        # The _review category is always created.
        assert "_review" in cat_slugs
        # _DEFAULT_DOCTYPES is applied too.
        assert get_doctype_by_slug(conn, "rechnung") is not None
        assert get_doctype_by_slug(conn, "kontoauszug") is not None
        assert get_doctype_by_slug(conn, "letter") is not None


def test_init_seed_with_aliases_creates_alias_rows(tmp_path: Path):
    """Persons with aliases get individual alias rows that route via find_person_by_alias."""
    db = tmp_path / "aido.sqlite"
    seed = tmp_path / "seed.yaml"
    seed.write_text(
        """
persons:
  - slug: timo
    display_name: Timo
    aliases: [Timo Jakob, T. Jakob]
categories: []
doctypes: []
""".strip(),
        encoding="utf-8",
    )
    rc = cli_main(["init", "--db", str(db), "--seed", str(seed)])
    assert rc == 0
    with connect(db) as conn:
        person = get_person_by_slug(conn, "timo")
        assert person is not None
        aliases = {a.alias for a in list_aliases_for(conn, person.id)}
        assert aliases == {"Timo Jakob", "T. Jakob"}


def test_init_seed_uses_existing_review_category(tmp_path: Path):
    """If the seed declares _review explicitly, init does not create a duplicate."""
    db = tmp_path / "aido.sqlite"
    seed = tmp_path / "seed.yaml"
    seed.write_text(
        """
persons: []
categories:
  - slug: _review
    display_name: Needs Review
    is_review: true
doctypes: []
""".strip(),
        encoding="utf-8",
    )
    rc = cli_main(["init", "--db", str(db), "--seed", str(seed)])
    assert rc == 0
    with connect(db) as conn:
        review_cats = [
            c for c in list_categories(conn, include_inactive=True) if c.slug == "_review"
        ]
        assert len(review_cats) == 1
        assert review_cats[0].display_name == "Needs Review"
        assert review_cats[0].is_review is True


def test_status_prints_needs_review_count(tmp_path: Path, capsys):
    """`aido status` prints the current needs_review count for the configured DB."""
    db = tmp_path / "aido.sqlite"
    archive = tmp_path / "archive"
    archive.mkdir()
    with connect(db) as conn:
        init_db(conn)
        timo = create_person(conn, slug="timo", display_name="Timo")
        cat = create_category(conn, slug="rechnungen", display_name="Rechnungen")
        dt = create_doctype(conn, slug="rechnung", display_name="Rechnung")
        # Two decisions, one needs review, one not.
        for hash_, needs_review in [("h1", True), ("h2", False)]:
            insert_decision(
                conn,
                NewDecision(
                    created_at=datetime(2026, 5, 17, 10, tzinfo=UTC),
                    source_hash=hash_,
                    source_path=f"/s/{hash_}.pdf",
                    filed_path=str(archive / f"{hash_}.pdf"),
                    person_id=timo.id,
                    category_id=cat.id,
                    doctype_id=dt.id,
                    document_date=date(2026, 3, 12),
                    counterparty="x",
                    proposed_filename=f"{hash_}.pdf",
                    overall_confidence=0.9,
                    person_confidence=0.9,
                    category_confidence=0.9,
                    reasoning="r",
                    classifier_model="m",
                    new_category_proposal=None,
                    needs_review=needs_review,
                    status=(DecisionStatus.REVIEW if needs_review else DecisionStatus.AUTO_FILED),
                ),
            )
    rc = cli_main(["status", "--db", str(db)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "needs_review: 1" in captured.out


def test_rebuild_index_is_noop_and_returns_zero(tmp_path: Path, capsys):
    """`rebuild-index` is documented as a v1 placeholder: returns 0 and notes itself on stderr."""
    db = tmp_path / "aido.sqlite"
    # The DB doesn't need to exist for the placeholder to succeed.
    rc = cli_main(["rebuild-index", "--db", str(db)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "rebuild-index" in captured.err
    # No DB file should be created since the command is a no-op.
    assert not db.exists()


def test_interactive_seed_creates_persons_aliases_and_shared(tmp_path: Path, monkeypatch):
    """Without --seed, init prompts for four persons + auto-creates the 'shared' bucket."""
    db = tmp_path / "aido.sqlite"
    # Four persons: only the first two are real, third is blank (skipped),
    # fourth duplicates the first slug (skipped). Aliases for person 1.
    inputs = iter(
        [
            "timo",  # person 1 slug
            "Timo Jakob",  # person 1 display name
            "Timo, T. Jakob",  # person 1 aliases (comma-separated)
            "anna",  # person 2 slug
            "",  # person 2 display name → falls back to slug
            "",  # person 2 aliases → none
            "",  # person 3 slug → skipped (blank)
            "timo",  # person 4 slug → duplicate of person 1, skipped
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))
    rc = cli_main(["init", "--db", str(db)])
    assert rc == 0
    with connect(db) as conn:
        slugs = {p.slug for p in list_persons(conn)}
        # 'timo' + 'anna' + 'shared' (auto-added).
        assert slugs == {"timo", "anna", "shared"}

        anna = get_person_by_slug(conn, "anna")
        assert anna is not None
        assert anna.display_name == "anna"  # blank display → slug fallback
        assert anna.is_shared is False

        shared = get_person_by_slug(conn, "shared")
        assert shared is not None
        assert shared.is_shared is True

        timo = get_person_by_slug(conn, "timo")
        assert timo is not None
        aliases = {a.alias for a in list_aliases_for(conn, timo.id)}
        assert aliases == {"Timo", "T. Jakob"}


def test_interactive_seed_does_not_duplicate_shared_when_user_added_it(tmp_path: Path, monkeypatch):
    """If the user already named a 'shared' person, init must not overwrite it."""
    db = tmp_path / "aido.sqlite"
    inputs = iter(
        [
            "shared",  # person 1 slug
            "Family",  # display name
            "",  # aliases
            "",  # person 2 skipped
            "",  # person 3 skipped
            "",  # person 4 skipped
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))
    rc = cli_main(["init", "--db", str(db)])
    assert rc == 0
    with connect(db) as conn:
        shared = get_person_by_slug(conn, "shared")
        assert shared is not None
        # User-provided display name preserved; not overwritten by the
        # auto-create branch ("Shared").
        assert shared.display_name == "Family"
        # is_shared was NOT auto-set because the user created the row before
        # the auto-create branch ran. This documents current behaviour.
        assert shared.is_shared is False


def test_init_without_subcommand_exits_with_argparse_error(capsys):
    """Argparse rejects an empty argv because `cmd` is a required subparser."""
    with pytest.raises(SystemExit) as excinfo:
        cli_main([])
    # argparse exits with code 2 for usage errors.
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "required" in err.lower() or "usage" in err.lower()
