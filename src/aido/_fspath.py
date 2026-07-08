"""Validation for operator-supplied filesystem paths.

Every path that reaches a filesystem sink from a CLI argument or a config
file first passes through :func:`validated_fs_path`. This is the "validate
the constructed path before accessing the file system" control that Sonar's
taint rules (``pythonsecurity:S8707`` / ``pythonsecurity:S8706``) ask for:
an empty string or a NUL byte -- neither of which is ever a legitimate
operator path -- is rejected before any I/O, and the value is canonicalized
so downstream operations act on a resolved absolute path rather than the
raw argument. It is behaviour-preserving for every well-formed path (the
resolved path points at the same target) while giving the reader a single,
auditable boundary for path handling.
"""

from __future__ import annotations

import os
from pathlib import Path


def validated_fs_path(raw: str | os.PathLike[str]) -> Path:
    """Return a canonical :class:`~pathlib.Path` for an operator-supplied path.

    Raises:
        ValueError: if the path is empty or contains a NUL byte.
    """
    text = os.fspath(raw)
    if not text or "\x00" in text:
        raise ValueError(f"invalid filesystem path: {text!r}")
    return Path(text).expanduser().resolve()
