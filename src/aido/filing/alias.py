"""Name and slug normalisation utilities.

`alias_normalize` produces a lowercased, accent-stripped key suitable for the
`person_aliases.alias_normalized` UNIQUE column. `slugify` produces a
filesystem-safe slug (lowercased, hyphen-separated, ASCII-only) used in
filenames and folder paths.
"""
from __future__ import annotations

import re
import unicodedata

_GERMAN_MAP = {
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "Ä": "ae", "Ö": "oe", "Ü": "ue",
    "œ": "oe", "Œ": "oe",
    "æ": "ae", "Æ": "ae",
}


def _transliterate(text: str) -> str:
    """Replace German + Latin ligatures, then strip remaining diacritics."""
    out = []
    for ch in text:
        if ch in _GERMAN_MAP:
            out.append(_GERMAN_MAP[ch])
        else:
            out.append(ch)
    s = "".join(out)
    # NFKD splits accented letters into base + combining mark; we drop the mark.
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def alias_normalize(name: str) -> str:
    """Normalise a person name for storage in `alias_normalized`.

    Lowercases, transliterates German/Latin special chars, collapses internal
    whitespace, strips leading/trailing whitespace. Keeps `.` so initials
    survive (e.g., 't. jakob').
    """
    s = _transliterate(name).lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s


def slugify(text: str, *, max_length: int = 80) -> str:
    """Produce a filesystem-safe slug.

    Lowercase, ASCII-only via transliteration, non-alphanum/hyphen chars
    collapsed to single hyphens, leading/trailing hyphens stripped, truncated
    to `max_length`.
    """
    s = _transliterate(text).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    if len(s) > max_length:
        s = s[:max_length].rstrip("-")
    return s
