from pathlib import Path

from aido.cli import main as cli_main
from aido.store.connection import connect
from aido.store.persons import find_person_by_alias, list_persons
from aido.store.taxonomy import (
    get_doctype_by_slug,
    get_review_category,
    list_categories,
)


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
