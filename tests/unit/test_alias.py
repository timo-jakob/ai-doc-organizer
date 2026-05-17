import pytest

from aido.filing.alias import alias_normalize, slugify


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Jakob", "jakob"),
        ("Jacob", "jacob"),
        ("Penélope", "penelope"),
        ("Penelope", "penelope"),
        ("Pénélope Müller", "penelope mueller"),
        ("Timo Jakob", "timo jakob"),
        ("  T.  Jakob ", "t. jakob"),
        ("Straße", "strasse"),
        ("Ärger", "aerger"),
        ("Œuvre", "oeuvre"),
        ("", ""),
    ],
)
def test_alias_normalize(raw: str, expected: str) -> None:
    assert alias_normalize(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Telekom", "telekom"),
        ("Stadt München", "stadt-muenchen"),
        ("E.ON Energie", "e-on-energie"),
        ("DKB AG", "dkb-ag"),
        ("  multi   spaces  ", "multi-spaces"),
        ("--leading-and-trailing--", "leading-and-trailing"),
        ("café-é-è", "cafe-e-e"),
        ("", ""),
        ("???", ""),
    ],
)
def test_slugify(raw: str, expected: str) -> None:
    assert slugify(raw) == expected


def test_slugify_truncates_to_length():
    long = "a" * 200
    assert len(slugify(long, max_length=50)) == 50
