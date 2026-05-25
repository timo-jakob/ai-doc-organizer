import time
from pathlib import Path

from aido.worker.queue import InboxQueue
from aido.worker.watcher import InboxWatcher


def _wait_for(predicate, timeout=5.0, interval=0.1):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def test_watcher_picks_up_new_pdf(tmp_path: Path):
    q = InboxQueue()
    watcher = InboxWatcher(inbox=tmp_path, queue=q, poll_interval=0.2)
    watcher.start()
    try:
        # Drop a PDF after the watcher is running.
        target = tmp_path / "new.pdf"
        target.write_bytes(b"%PDF-1.4\n%fake\n")
        assert _wait_for(lambda: q.get(timeout=0.1) is not None or False, timeout=4.0) or _wait_for(
            lambda: target.exists() and q._q.qsize() >= 1, timeout=4.0
        )  # type: ignore[attr-defined]
    finally:
        watcher.stop()


def test_watcher_ignores_non_pdfs(tmp_path: Path):
    q = InboxQueue()
    watcher = InboxWatcher(inbox=tmp_path, queue=q, poll_interval=0.2)
    watcher.start()
    try:
        (tmp_path / "note.txt").write_text("hi")
        time.sleep(1.0)
        assert q.get(timeout=0.1) is None
    finally:
        watcher.stop()


def test_watcher_ignores_hidden_files(tmp_path: Path):
    q = InboxQueue()
    watcher = InboxWatcher(inbox=tmp_path, queue=q, poll_interval=0.2)
    watcher.start()
    try:
        (tmp_path / ".hidden.pdf").write_bytes(b"%PDF-1.4")
        time.sleep(1.0)
        assert q.get(timeout=0.1) is None
    finally:
        watcher.stop()
