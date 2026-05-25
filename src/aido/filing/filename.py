"""Filename construction and collision handling."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from aido.filing.alias import slugify

_STEM_MAX = 80
_DOCTYPE_FALLBACK = "letter"
_PARTY_FALLBACK = "unknown"


def build_filename(doc_date: date, doctype: str, counterparty: str) -> str:
    """Return the canonical filename for a classified document.

    Format: ``YYYY-MM-DD_<doctype>_<counterparty>.pdf``. Empty doctype falls
    back to 'letter'; empty counterparty falls back to 'unknown'. The stem is
    truncated to 80 characters (counterparty is the first to lose).
    """
    doctype_slug = slugify(doctype) or _DOCTYPE_FALLBACK
    party_slug = slugify(counterparty) or _PARTY_FALLBACK
    date_part = doc_date.isoformat()
    fixed = f"{date_part}_{doctype_slug}_"
    budget = _STEM_MAX - len(fixed)
    if budget < 1:
        # Pathological doctype length — keep at least one char of counterparty.
        budget = 1
    party_slug = party_slug[:budget].rstrip("-") or _PARTY_FALLBACK[:budget]
    return f"{fixed}{party_slug}.pdf"


def next_available_name(target: Path, *, max_attempts: int = 1000) -> Path:
    """Return `target` unchanged if it does not exist, else append `_2`, `_3`, ...

    Raises FileExistsError if more than `max_attempts` collisions are found.
    """
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    parent = target.parent
    for i in range(2, max_attempts + 1):
        candidate = parent / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"Could not find a free name for {target} after {max_attempts} attempts")
