"""Main entrypoint: wires config → daemon → web UI and runs them together."""

from __future__ import annotations

import argparse
import os
import signal
import sqlite3
import sys
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from aido.classifier.factory import build_classifier
from aido.config import ClassifierBackend, Config, load_config
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


EX_CONFIG = 78  # BSD sysexits.h: configuration error


def _preflight_fail(message: str) -> None:
    print(f"aido: config error: {message}", file=sys.stderr)
    raise SystemExit(EX_CONFIG)


def _preflight(config_path: Path) -> Config:
    """Validate the environment before starting the daemon.

    Exits with EX_CONFIG (78) and a one-line plain-text message on stderr for
    each known misconfiguration, instead of letting the daemon crash later
    with a cryptic traceback.
    """
    if config_path.is_dir():
        _preflight_fail(
            f"{config_path} is a directory, not a file — Docker creates an empty "
            "directory when the bind-mount source is missing; create the config "
            "file on the host and restart"
        )

    cfg = load_config(config_path)

    if (
        cfg.classifier.backend == ClassifierBackend.ANTHROPIC_API
        and not os.environ.get("ANTHROPIC_API_KEY", "").strip()
    ):
        _preflight_fail(
            "classifier.backend is 'anthropic_api' but ANTHROPIC_API_KEY is "
            "unset or blank — set it in the container environment"
        )

    if not os.access(cfg.archive_root, os.W_OK):
        _preflight_fail(
            f"archive_root {cfg.archive_root} is not writable — check that the "
            "directory exists and the bind mount allows writes"
        )

    if not cfg.scan_inbox.is_dir() or not os.access(cfg.scan_inbox, os.R_OK):
        _preflight_fail(
            f"scan_inbox {cfg.scan_inbox} does not exist or is not readable — "
            "check the scanner share bind mount"
        )

    if not os.access(cfg.db_path.parent, os.W_OK):
        _preflight_fail(
            f"db_path parent directory {cfg.db_path.parent} is not writable — "
            "the daemon cannot create or open its SQLite database there"
        )

    return cfg


def build_runtime(*, config_path: Path, pidfile: Path) -> RuntimeContext:
    cfg = _preflight(config_path)
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
