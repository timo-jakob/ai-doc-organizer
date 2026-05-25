"""Watchdog-based file watcher that pushes PDFs to an InboxQueue.

We pin to `PollingObserver` because the daemon runs in a Docker container on
macOS where host bind-mounts do not emit inotify events.
"""

from __future__ import annotations

import logging
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers.polling import PollingObserver

from aido.worker.queue import InboxQueue

_log = logging.getLogger("aido.watcher")


def _is_pdf(path: Path) -> bool:
    return path.is_file() and not path.name.startswith(".") and path.suffix.lower() == ".pdf"


class _Handler(FileSystemEventHandler):
    def __init__(self, queue: InboxQueue) -> None:
        self._queue = queue

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if _is_pdf(path):
            _log.info("watcher.enqueue", extra={"source_path": str(path)})
            self._queue.put(path)

    def on_moved(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = Path(event.dest_path)
        if _is_pdf(path):
            _log.info("watcher.enqueue", extra={"source_path": str(path)})
            self._queue.put(path)


class InboxWatcher:
    """Run a PollingObserver against `inbox`, enqueueing new PDFs."""

    def __init__(self, *, inbox: Path, queue: InboxQueue, poll_interval: float = 2.0) -> None:
        self._inbox = inbox
        self._queue = queue
        self._observer = PollingObserver(timeout=poll_interval)
        self._handler = _Handler(queue)

    def start(self) -> None:
        self._inbox.mkdir(parents=True, exist_ok=True)
        self._observer.schedule(self._handler, str(self._inbox), recursive=False)
        self._observer.start()

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join(timeout=5)
