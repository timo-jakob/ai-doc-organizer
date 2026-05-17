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


def _transliterate(text: str, *, keep_umlaut_ligatures: bool = False) -> str:
    """Strip diacritics, with optional special-char handling.

    By default, applies the German map to all characters (ü -> ue, ß -> ss, etc).
    If keep_umlaut_ligatures=True, skips German map for umlaut chars (ä ö ü Ä Ö Ü),
    leaving them for NFD decomposition instead. Always applies map to non-decomposable
    ligatures like ß, œ, æ.
    """
    # Apply German map selectively or fully.
    out = []
    for ch in text:
        if ch in _GERMAN_MAP:
            # Skip umlaut transliteration if keep_umlaut_ligatures is set.
            if keep_umlaut_ligatures and ch in "äöüÄÖÜ":
                out.append(ch)
            else:
                out.append(_GERMAN_MAP[ch])
        else:
            out.append(ch)
    s = "".join(out)

    # NFD decomposes accented letters into base + combining diacritics.
    # We drop the diacritics, leaving only the base characters.
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def alias_normalize(name: str) -> str:
    """Normalise a person name for storage in `alias_normalized`.

    Lowercases, strips diacritics (accent-insensitive matching), collapses internal
    whitespace, strips leading/trailing whitespace. Keeps `.` so initials survive
    (e.g., 't. jakob'). Umlauts (ä ö ü) decompose to base chars (a o u) for
    accent-insensitive matching; non-decomposable ligatures like ß, œ are converted.
    """
    s = _transliterate(name, keep_umlaut_ligatures=True).lower()
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
