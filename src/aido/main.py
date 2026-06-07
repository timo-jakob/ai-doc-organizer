"""Main entrypoint: wires config → daemon → web UI and runs them together."""

from __future__ import annotations

import argparse
import signal
import sqlite3
import sys
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from aido.classifier.factory import build_classifier
from aido.config import Config, load_config
from aido.daemon import Daemon
from aido.logging_setup import configure_logging
from aido.webui.app import WebState, create_app


@dataclass
class RuntimeContext:
    config: Config
    daemon: Daemon
    app: object  # Flask
    state: WebState
    _conn: sqlite3.Connection
    _conn_ctx: object

    def shutdown(self) -> None:
        self.daemon.stop()


def build_runtime(*, config_path: Path, pidfile: Path) -> RuntimeContext:
    cfg = load_config(config_path)
    configure_logging(cfg.log_path)

    daemon = Daemon(
        db_path=cfg.db_path,
        archive_root=cfg.archive_root,
        inbox=cfg.scan_inbox,
        classifier_factory=lambda conn: build_classifier(conn, cfg.classifier),
        threshold=cfg.classifier.review_confidence_threshold,
        classifier_model=cfg.classifier.model,
        pidfile=pidfile,
    )
    daemon.start()

    # WebState shares the daemon's connection + mutation context so both the
    # worker thread and HTTP handlers serialize through the same lock.
    state = WebState(
        db_path=cfg.db_path,
        archive_root=cfg.archive_root,
        mutations=daemon._mutations,  # type: ignore[attr-defined]
        health=daemon.health,
    )
    app = create_app(state)
    return RuntimeContext(
        config=cfg,
        daemon=daemon,
        app=app,
        state=state,
        _conn=daemon._conn,  # type: ignore[attr-defined]
        _conn_ctx=daemon._connection_ctx,  # type: ignore[attr-defined]
    )


def run(
    *,
    config_path: Path,
    pidfile: Path,
    ready_event: threading.Event | None = None,
    stop_event: threading.Event | None = None,
    run_web: bool = True,
) -> RuntimeContext:
    """Build the runtime, run web UI in main thread, return after shutdown.

    `ready_event` / `stop_event` are used by tests to coordinate startup +
    shutdown without actually starting Flask. `run_web=False` skips Flask
    entirely (the daemon worker still runs).
    """
    rt = build_runtime(config_path=config_path, pidfile=pidfile)

    if ready_event is not None:
        ready_event.set()

    if run_web:

        def _sigterm(*_):
            rt.shutdown()
            sys.exit(0)

        signal.signal(signal.SIGTERM, _sigterm)
        signal.signal(signal.SIGINT, _sigterm)
        try:
            rt.app.run(  # type: ignore[attr-defined]
                host=rt.config.web.bind,
                port=rt.config.web.port,
                threaded=True,
                use_reloader=False,
            )
        finally:
            rt.shutdown()
    elif stop_event is not None:
        stop_event.wait()
        rt.shutdown()
    return rt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aido-daemon")
    parser.add_argument("--config", type=Path, default=Path("/app/config.yaml"))
    parser.add_argument("--pidfile", type=Path, default=Path("/var/run/aido.pid"))
    args = parser.parse_args(argv)
    run(config_path=args.config, pidfile=args.pidfile)
    return 0


if __name__ == "__main__":
    sys.exit(main())
