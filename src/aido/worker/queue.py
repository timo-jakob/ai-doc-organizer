"""Single-producer queue between watcher and worker."""
from __future__ import annotations

import queue
from pathlib import Path


class InboxQueue:
    """Thread-safe FIFO of paths for the worker to process."""

    def __init__(self) -> None:
        self._q: queue.Queue[Path] = queue.Queue()

    def put(self, path: Path) -> None:
        self._q.put(path)

    def get(self, timeout: float = 1.0) -> Path | None:
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None

    def drain_existing(self, inbox: Path) -> None:
        """Enqueue every top-level PDF currently in `inbox`. Skips dotfiles."""
        for entry in sorted(inbox.iterdir()):
            if entry.is_file() and not entry.name.startswith(".") \
                    and entry.suffix.lower() == ".pdf":
                self.put(entry)
