"""aido daemon: wires watcher + queue + worker + classifier; tracks health."""

from __future__ import annotations

import contextlib
import os
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from aido.classifier.base import Classifier
from aido.mutations import MutationContext
from aido.store.connection import connect
from aido.store.migrations import init_db
from aido.worker.pipeline import Pipeline, PipelineOutcome
from aido.worker.queue import InboxQueue
from aido.worker.watcher import InboxWatcher


class HealthStatus(StrEnum):
    OK = "ok"
    AUTH_FAILED = "auth_failed"
    CANNOT_WRITE = "cannot_write"
    DEGRADED = "degraded"


@dataclass
class HealthState:
    status: HealthStatus = HealthStatus.OK
    last_classification_at: datetime | None = None
    consecutive_failures: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record_outcome(self, outcome: PipelineOutcome, *, now: datetime) -> None:
        with self._lock:
            if outcome in (PipelineOutcome.AUTO_FILED, PipelineOutcome.REVIEW):
                self.consecutive_failures = 0
                self.last_classification_at = now
                if self.status == HealthStatus.DEGRADED:
                    self.status = HealthStatus.OK
            elif outcome == PipelineOutcome.FAILED:
                self.consecutive_failures += 1
                if self.consecutive_failures >= 3:
                    self.status = HealthStatus.DEGRADED

    def set(self, status: HealthStatus) -> None:
        with self._lock:
            self.status = status


class Daemon:
    """Long-running coordinator. `start()` spawns threads; `stop()` joins them."""

    def __init__(
        self,
        *,
        db_path: Path,
        archive_root: Path,
        inbox: Path,
        classifier_factory: Callable[[sqlite3.Connection], Classifier],
        threshold: float,
        classifier_model: str,
        pidfile: Path,
        poll_interval: float = 2.0,
        stabilize_seconds: float = 2.0,
    ) -> None:
        self._db_path = db_path
        self._archive_root = archive_root
        self._inbox = inbox
        self._classifier_factory = classifier_factory
        self._threshold = threshold
        self._classifier_model = classifier_model
        self._pidfile = pidfile
        self._poll_interval = poll_interval
        self._stabilize_seconds = stabilize_seconds

        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._watcher: InboxWatcher | None = None
        self._queue = InboxQueue()
        self.health = HealthState()
        self._conn: sqlite3.Connection | None = None
        self._mutations: MutationContext | None = None

    # ---- lifecycle ----------------------------------------------------

    def _acquire_pidfile(self) -> None:
        if self._pidfile.exists():
            try:
                pid = int(self._pidfile.read_text().strip())
            except ValueError:
                pid = -1
            if pid > 0 and _process_alive(pid):
                raise RuntimeError(f"aido already running (pid {pid})")
        self._pidfile.parent.mkdir(parents=True, exist_ok=True)
        self._pidfile.write_text(str(os.getpid()))

    def _release_pidfile(self) -> None:
        with contextlib.suppress(OSError):
            self._pidfile.unlink(missing_ok=True)

    def start(self) -> None:
        self._acquire_pidfile()
        self._archive_root.mkdir(parents=True, exist_ok=True)
        self._inbox.mkdir(parents=True, exist_ok=True)
        ctx = connect(self._db_path)
        self._conn = ctx.__enter__()
        self._connection_ctx = ctx
        init_db(self._conn)

        self._mutations = MutationContext(
            conn=self._conn,
            archive_root=self._archive_root,
            lock=threading.Lock(),
            now=lambda: datetime.now(UTC),
        )

        classifier = self._classifier_factory(self._conn)
        pipeline = Pipeline(
            conn=self._conn,
            classifier=classifier,
            threshold=self._threshold,
            mutations=self._mutations,
            classifier_model=self._classifier_model,
            stabilize_seconds=self._stabilize_seconds,
        )

        self._queue.drain_existing(self._inbox)
        self._watcher = InboxWatcher(
            inbox=self._inbox, queue=self._queue, poll_interval=self._poll_interval
        )
        self._watcher.start()

        self._worker_thread = threading.Thread(
            target=self._worker_loop, args=(pipeline,), daemon=True, name="aido-worker"
        )
        self._worker_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._watcher is not None:
            self._watcher.stop()
        if self._worker_thread is not None:
            self._worker_thread.join(timeout=10)
        if self._conn is not None:
            try:
                self._connection_ctx.__exit__(None, None, None)
            finally:
                self._conn = None
        self._release_pidfile()

    # ---- worker loop --------------------------------------------------

    def _worker_loop(self, pipeline: Pipeline) -> None:
        while not self._stop_event.is_set():
            path = self._queue.get(timeout=0.5)
            if path is None:
                continue
            outcome = pipeline.process(path)
            self.health.record_outcome(outcome, now=datetime.now(UTC))


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
