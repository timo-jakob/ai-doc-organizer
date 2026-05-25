"""Atomic move of a PDF into the archive under <person>/<category>/."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from aido.filing.filename import next_available_name


@dataclass(frozen=True, slots=True)
class FilingTarget:
    """Where a document should land.

    `person_slug` is None for documents going into the top-level `_review/`
    bucket. `category_slug='_review'` + `person_slug=None` is the conventional
    pairing for the review bucket; other combinations are allowed but produce
    `<archive>/<person>/<category>/`.
    """

    person_slug: str | None
    category_slug: str
    filename: str


def _resolve_dir(archive_root: Path, target: FilingTarget) -> Path:
    if target.person_slug is None:
        return archive_root / target.category_slug
    return archive_root / target.person_slug / target.category_slug


def file_document(
    src: Path,
    *,
    archive_root: Path,
    target: FilingTarget,
) -> Path:
    """Move `src` to the resolved location inside `archive_root`.

    Creates parent directories as needed; resolves filename collisions by
    appending `_2`, `_3`, .... Uses `os.replace` when src and dest are on the
    same filesystem (atomic rename); falls back to `shutil.move` for the
    cross-filesystem case (e.g., two separate Docker bind mounts).
    """
    dest_dir = _resolve_dir(archive_root, target)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = next_available_name(dest_dir / target.filename)
    resolved_root = archive_root.resolve()
    if not dest.resolve().is_relative_to(resolved_root):
        raise ValueError(f"Destination {dest} escapes archive root {resolved_root}")
    try:
        os.replace(src, dest)
    except OSError as e:
        if e.errno == 18:  # EXDEV: cross-device link
            shutil.move(str(src), str(dest))
        else:
            raise
    return dest
