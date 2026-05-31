"""Direct unit tests for `aido.worker.watcher._Handler`.

The integration tests (`tests/integration/test_watcher.py`) cover the polling
observer end-to-end. These tests exercise the handler's branches without
depending on the observer's timing:

- `on_created` / `on_moved` early-return for directory events.
- `on_moved` enqueues the destination path for PDFs and ignores non-PDFs.
"""

from __future__ import annotations

from pathlib import Path

from watchdog.events import (
    DirCreatedEvent,
    DirMovedEvent,
    FileCreatedEvent,
    FileMovedEvent,
)

from aido.worker.queue import InboxQueue
from aido.worker.watcher import _Handler


def _drain(q: InboxQueue) -> list[Path]:
    out: list[Path] = []
    while True:
        item = q.get(timeout=0.0)
        if item is None:
            return out
        out.append(item)


def test_on_created_ignores_directory_events(tmp_path: Path) -> None:
    """A new subdirectory in the inbox must not be enqueued.

    `watcher.py` line 30: `if event.is_directory: return`.
    """
    q = InboxQueue()
    handler = _Handler(q)
    subdir = tmp_path / "subdir"
    subdir.mkdir()

    handler.on_created(DirCreatedEvent(str(subdir)))

    assert _drain(q) == []


def test_on_moved_enqueues_pdf_at_destination(tmp_path: Path) -> None:
    """A rename whose destination is a real PDF must enqueue that destination.

    `watcher.py` lines 36-42: the `on_moved` handler. The watcher uses
    `event.dest_path` (where the file ended up), not `src_path`.
    """
    q = InboxQueue()
    handler = _Handler(q)

    src = tmp_path / "tmp.partial"
    dest = tmp_path / "ready.pdf"
    dest.write_bytes(b"%PDF-1.4\n%fake\n")

    handler.on_moved(FileMovedEvent(str(src), str(dest)))

    items = _drain(q)
    assert items == [dest]


def test_on_moved_ignores_non_pdf_destination(tmp_path: Path) -> None:
    """`on_moved` must skip non-PDF destinations even if a file is there.

    Confirms the `_is_pdf` filter applies on the moved-path branch too.
    """
    q = InboxQueue()
    handler = _Handler(q)

    src = tmp_path / "tmp.partial"
    dest = tmp_path / "note.txt"
    dest.write_text("hi")

    handler.on_moved(FileMovedEvent(str(src), str(dest)))

    assert _drain(q) == []


def test_on_moved_ignores_directory_events(tmp_path: Path) -> None:
    """Renaming a directory must not enqueue anything.

    `watcher.py` line 37: `on_moved`'s `if event.is_directory: return`.
    """
    q = InboxQueue()
    handler = _Handler(q)

    src_dir = tmp_path / "old_dir"
    dest_dir = tmp_path / "new_dir"
    dest_dir.mkdir()

    handler.on_moved(DirMovedEvent(str(src_dir), str(dest_dir)))

    assert _drain(q) == []


def test_on_moved_ignores_hidden_pdf_destination(tmp_path: Path) -> None:
    """A move whose destination starts with `.` must not enqueue."""
    q = InboxQueue()
    handler = _Handler(q)

    src = tmp_path / "tmp.partial"
    dest = tmp_path / ".hidden.pdf"
    dest.write_bytes(b"%PDF-1.4\n%fake\n")

    handler.on_moved(FileMovedEvent(str(src), str(dest)))

    assert _drain(q) == []


def test_on_created_enqueues_pdf_via_direct_event(tmp_path: Path) -> None:
    """Sanity: directly invoking on_created with a FileCreatedEvent enqueues.

    The integration tests cover this via the real observer; this version is
    deterministic and runs without timing concerns.
    """
    q = InboxQueue()
    handler = _Handler(q)
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%fake\n")

    handler.on_created(FileCreatedEvent(str(pdf)))

    assert _drain(q) == [pdf]
