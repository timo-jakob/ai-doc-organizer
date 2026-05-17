import threading
import time
from pathlib import Path

import pytest

from aido.main import RuntimeContext, build_runtime


def _write_config(path: Path, *, archive, inbox, db, log) -> Path:
    path.write_text(f"""
archive_root: {archive}
scan_inbox: {inbox}
db_path: {db}
log_path: {log}

classifier:
  backend: fake
  model: claude-opus-4-7
  review_confidence_threshold: 0.75

web:
  bind: 127.0.0.1
  port: 0
""".strip(), encoding="utf-8")
    return path


def test_build_runtime_returns_wired_context(tmp_path: Path):
    archive = tmp_path / "archive"
    inbox = tmp_path / "inbox"
    archive.mkdir(); inbox.mkdir()
    cfg = _write_config(
        tmp_path / "config.yaml",
        archive=archive, inbox=inbox,
        db=tmp_path / "aido.sqlite", log=tmp_path / "aido.log",
    )

    rt = build_runtime(config_path=cfg, pidfile=tmp_path / "aido.pid")
    assert isinstance(rt, RuntimeContext)
    assert rt.daemon is not None
    assert rt.app is not None
    # Don't actually run Flask in the test; just confirm the app has our routes.
    routes = {r.rule for r in rt.app.url_map.iter_rules()}
    assert "/" in routes
    assert "/healthz" in routes
    assert "/settings" in routes
    # Clean up the daemon's DB context so the temp dir can be removed.
    rt.shutdown()


def test_main_entrypoint_starts_and_stops(tmp_path: Path):
    """Sanity: invoking aido.main.run() in a thread and signalling stop
    should exit cleanly without leaving the pidfile behind.
    """
    archive = tmp_path / "archive"
    inbox = tmp_path / "inbox"
    archive.mkdir(); inbox.mkdir()
    cfg = _write_config(
        tmp_path / "config.yaml",
        archive=archive, inbox=inbox,
        db=tmp_path / "aido.sqlite", log=tmp_path / "aido.log",
    )
    pidfile = tmp_path / "aido.pid"

    from aido.main import run

    started = threading.Event()
    stopped = threading.Event()
    rt_holder: dict = {}

    def runner():
        rt_holder["rt"] = run(
            config_path=cfg, pidfile=pidfile,
            ready_event=started, stop_event=stopped, run_web=False,
        )

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    assert started.wait(timeout=5)
    assert pidfile.exists()
    stopped.set()
    t.join(timeout=10)
    assert not t.is_alive()
    assert not pidfile.exists()
