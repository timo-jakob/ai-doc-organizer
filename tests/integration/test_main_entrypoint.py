import threading
from pathlib import Path

import pytest

from aido.main import RuntimeContext, build_runtime


def _write_config(path: Path, *, archive, inbox, db, log, backend: str = "fake") -> Path:
    path.write_text(
        f"""
archive_root: {archive}
scan_inbox: {inbox}
db_path: {db}
log_path: {log}

classifier:
  backend: {backend}
  model: claude-opus-4-7
  review_confidence_threshold: 0.75

web:
  bind: 127.0.0.1
  port: 8765
""".strip(),
        encoding="utf-8",
    )
    return path


def test_build_runtime_returns_wired_context(tmp_path: Path):
    archive = tmp_path / "archive"
    inbox = tmp_path / "inbox"
    archive.mkdir()
    inbox.mkdir()
    cfg = _write_config(
        tmp_path / "config.yaml",
        archive=archive,
        inbox=inbox,
        db=tmp_path / "aido.sqlite",
        log=tmp_path / "aido.log",
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


def test_preflight_fails_when_config_path_is_directory(tmp_path: Path, capsys):
    """Docker auto-creates an empty directory when the bind-mount source is
    missing; the daemon should exit 78 with a clear message, not traceback."""
    config_dir = tmp_path / "config.yaml"
    config_dir.mkdir()

    with pytest.raises(SystemExit) as excinfo:
        build_runtime(config_path=config_dir, pidfile=tmp_path / "aido.pid")

    assert excinfo.value.code == 78
    err = capsys.readouterr().err
    assert str(config_dir) in err
    assert "is a directory" in err


@pytest.mark.parametrize("key_value", [None, "", "   "])
def test_preflight_fails_when_anthropic_key_missing(tmp_path: Path, capsys, monkeypatch, key_value):
    archive = tmp_path / "archive"
    inbox = tmp_path / "inbox"
    archive.mkdir()
    inbox.mkdir()
    cfg = _write_config(
        tmp_path / "config.yaml",
        archive=archive,
        inbox=inbox,
        db=tmp_path / "aido.sqlite",
        log=tmp_path / "aido.log",
        backend="anthropic_api",
    )
    if key_value is None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    else:
        monkeypatch.setenv("ANTHROPIC_API_KEY", key_value)

    with pytest.raises(SystemExit) as excinfo:
        build_runtime(config_path=cfg, pidfile=tmp_path / "aido.pid")

    assert excinfo.value.code == 78
    err = capsys.readouterr().err
    assert "ANTHROPIC_API_KEY" in err
    assert "anthropic_api" in err


@pytest.mark.parametrize("mode", ["missing", "readonly"])
def test_preflight_fails_when_archive_root_not_writable(tmp_path: Path, capsys, mode):
    archive = tmp_path / "archive"
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    if mode == "readonly":
        archive.mkdir()
        archive.chmod(0o500)
    cfg = _write_config(
        tmp_path / "config.yaml",
        archive=archive,
        inbox=inbox,
        db=tmp_path / "aido.sqlite",
        log=tmp_path / "aido.log",
    )

    try:
        with pytest.raises(SystemExit) as excinfo:
            build_runtime(config_path=cfg, pidfile=tmp_path / "aido.pid")
        assert excinfo.value.code == 78
        err = capsys.readouterr().err
        assert "archive_root" in err
        assert str(archive) in err
    finally:
        if mode == "readonly":
            archive.chmod(0o700)


@pytest.mark.parametrize("mode", ["missing", "unreadable"])
def test_preflight_fails_when_scan_inbox_not_readable(tmp_path: Path, capsys, mode):
    archive = tmp_path / "archive"
    inbox = tmp_path / "inbox"
    archive.mkdir()
    if mode == "unreadable":
        inbox.mkdir()
        inbox.chmod(0o000)
    cfg = _write_config(
        tmp_path / "config.yaml",
        archive=archive,
        inbox=inbox,
        db=tmp_path / "aido.sqlite",
        log=tmp_path / "aido.log",
    )

    try:
        with pytest.raises(SystemExit) as excinfo:
            build_runtime(config_path=cfg, pidfile=tmp_path / "aido.pid")
        assert excinfo.value.code == 78
        err = capsys.readouterr().err
        assert "scan_inbox" in err
        assert str(inbox) in err
    finally:
        if mode == "unreadable":
            inbox.chmod(0o700)


@pytest.mark.parametrize("mode", ["missing", "readonly"])
def test_preflight_fails_when_db_parent_not_writable(tmp_path: Path, capsys, mode):
    archive = tmp_path / "archive"
    inbox = tmp_path / "inbox"
    archive.mkdir()
    inbox.mkdir()
    db_parent = tmp_path / "data"
    if mode == "readonly":
        db_parent.mkdir()
        db_parent.chmod(0o500)
    cfg = _write_config(
        tmp_path / "config.yaml",
        archive=archive,
        inbox=inbox,
        db=db_parent / "aido.sqlite",
        log=tmp_path / "aido.log",
    )

    try:
        with pytest.raises(SystemExit) as excinfo:
            build_runtime(config_path=cfg, pidfile=tmp_path / "aido.pid")
        assert excinfo.value.code == 78
        err = capsys.readouterr().err
        assert "db_path" in err
        assert str(db_parent) in err
    finally:
        if mode == "readonly":
            db_parent.chmod(0o700)


def test_main_entrypoint_starts_and_stops(tmp_path: Path):
    """Sanity: invoking aido.main.run() in a thread and signalling stop
    should exit cleanly without leaving the pidfile behind.
    """
    archive = tmp_path / "archive"
    inbox = tmp_path / "inbox"
    archive.mkdir()
    inbox.mkdir()
    cfg = _write_config(
        tmp_path / "config.yaml",
        archive=archive,
        inbox=inbox,
        db=tmp_path / "aido.sqlite",
        log=tmp_path / "aido.log",
    )
    pidfile = tmp_path / "aido.pid"

    from aido.main import run

    started = threading.Event()
    stopped = threading.Event()
    rt_holder: dict = {}

    def runner():
        rt_holder["rt"] = run(
            config_path=cfg,
            pidfile=pidfile,
            ready_event=started,
            stop_event=stopped,
            run_web=False,
        )

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    assert started.wait(timeout=5)
    assert pidfile.exists()
    stopped.set()
    t.join(timeout=10)
    assert not t.is_alive()
    assert not pidfile.exists()
