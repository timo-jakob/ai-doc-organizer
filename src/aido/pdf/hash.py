"""SHA-256 of a file on disk, streaming so big files don't blow memory."""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK = 64 * 1024


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()
