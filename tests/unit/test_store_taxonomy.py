import pytest

from aido.store.connection import connect
from aido.store.migrations import init_db
from aido.store.taxonomy import (
    CategoryRow,
    DoctypeRow,
    create_category,
    create_doctype,
    get_category_by_slug,
    get_doctype_by_slug,
    get_review_category,
    list_categories,
    list_doctypes,
)


@pytest.fixture
def conn(tmp_path):
    with connect(tmp_path / "x.sqlite") as c:
        init_db(c)
        yield c


def test_create_and_get_category(conn):
    c = create_category(
        conn, slug="rechnungen", display_name="Rechnungen", description="Eingehende Rechnungen"
    )
    assert isinstance(c, CategoryRow)
    assert c.slug == "rechnungen"
    assert c.is_review is False

    assert get_category_by_slug(conn, "rechnungen") == c


def test_create_review_category(conn):
    c = create_category(conn, slug="_review", display_name="_review", is_review=True)
    assert c.is_review is True
    assert get_review_category(conn) == c


def test_list_categories_alphabetical_active_only(conn):
    create_category(conn, slug="steuer", display_name="Steuer")
    create_category(conn, slug="rechnungen", display_name="Rechnungen")
    create_category(conn, slug="archived", display_name="Archived", is_active=False)
    slugs = [c.slug for c in list_categories(conn)]
    assert slugs == ["rechnungen", "steuer"]
    slugs_all = [c.slug for c in list_categories(conn, include_inactive=True)]
    assert "archived" in slugs_all


def test_create_and_get_doctype(conn):
    d = create_doctype(
        conn,
        slug="rechnung",
        display_name="Rechnung",
        description="Eine Rechnung von einem Anbieter",
    )
    assert isinstance(d, DoctypeRow)
    assert get_doctype_by_slug(conn, "rechnung") == d


def test_list_doctypes(conn):
    create_doctype(conn, slug="rechnung", display_name="Rechnung")
    create_doctype(conn, slug="letter", display_name="Brief")
    slugs = [d.slug for d in list_doctypes(conn)]
    assert slugs == ["letter", "rechnung"]


def test_duplicate_slug_raises(conn):
    create_category(conn, slug="x", display_name="X")
    with pytest.raises(Exception):
        create_category(conn, slug="x", display_name="Y")
