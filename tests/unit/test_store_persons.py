import pytest

from aido.store.connection import connect
from aido.store.migrations import init_db
from aido.store.persons import (
    PersonRow,
    add_alias,
    create_person,
    find_person_by_alias,
    get_person_by_slug,
    list_aliases_for,
    list_persons,
)


@pytest.fixture
def conn(tmp_path):
    with connect(tmp_path / "x.sqlite") as c:
        init_db(c)
        yield c


def test_create_and_get_by_slug(conn):
    p = create_person(conn, slug="timo", display_name="Timo Jakob")
    assert isinstance(p, PersonRow)
    assert p.slug == "timo"
    assert p.display_name == "Timo Jakob"
    assert p.is_shared is False

    got = get_person_by_slug(conn, "timo")
    assert got == p


def test_create_shared(conn):
    p = create_person(conn, slug="shared", display_name="Shared", is_shared=True)
    assert p.is_shared is True


def test_list_persons_in_slug_order(conn):
    create_person(conn, slug="timo", display_name="Timo")
    create_person(conn, slug="anna", display_name="Anna")
    create_person(conn, slug="shared", display_name="Shared", is_shared=True)
    slugs = [p.slug for p in list_persons(conn)]
    assert slugs == ["anna", "shared", "timo"]


def test_add_alias_and_lookup_case_and_accent_insensitive(conn):
    p = create_person(conn, slug="penelope", display_name="Pénélope Müller")
    add_alias(conn, person_id=p.id, alias="Pénélope")
    add_alias(conn, person_id=p.id, alias="Penelope")
    add_alias(conn, person_id=p.id, alias="Müller")

    assert find_person_by_alias(conn, "penelope").id == p.id
    assert find_person_by_alias(conn, "PENÉLOPE").id == p.id
    assert find_person_by_alias(conn, " müller ").id == p.id
    assert find_person_by_alias(conn, "muller").id == p.id  # normalised match
    assert find_person_by_alias(conn, "unknown") is None


def test_alias_normalized_is_unique(conn):
    p1 = create_person(conn, slug="timo", display_name="Timo")
    p2 = create_person(conn, slug="other", display_name="Other")
    add_alias(conn, person_id=p1.id, alias="Jakob")
    with pytest.raises(Exception):  # IntegrityError under the hood
        add_alias(conn, person_id=p2.id, alias="jakob")


def test_list_aliases_for(conn):
    p = create_person(conn, slug="timo", display_name="Timo")
    add_alias(conn, person_id=p.id, alias="Jakob")
    add_alias(conn, person_id=p.id, alias="Jacob")
    aliases = list_aliases_for(conn, p.id)
    assert sorted(a.alias for a in aliases) == ["Jacob", "Jakob"]


def test_create_person_with_duplicate_slug_raises(conn):
    create_person(conn, slug="timo", display_name="Timo")
    with pytest.raises(Exception):
        create_person(conn, slug="timo", display_name="Other")
