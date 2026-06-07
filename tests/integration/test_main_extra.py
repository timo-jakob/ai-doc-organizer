"""Coverage for `aido.main` argv parsing + run_web signal handlers.

The happy-path `build_runtime` test lives in `test_main_entrypoint.py`. These
tests cover the missing branches:
- `run(run_web=True)` installs SIGINT/SIGTERM handlers and invokes Flask.
- `main(argv)` parses argv and delegates to `run`.
- The SIGTERM handler triggers `shutdown` and `sys.exit`.
"""

from __future__ import annotations

import signal
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _write_config(path: Path, *, archive, inbox, db, log) -> Path:
    path.write_text(
        f"""
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
""".strip(),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def cfg_paths(tmp_path: Path):
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
    return {"cfg": cfg, "pidfile": tmp_path / "aido.pid"}


def test_run_with_web_invokes_flask_and_cleans_up_on_return(cfg_paths, monkeypatch):
    """run(run_web=True) must:
      1. Build the runtime,
      2. Install signal handlers (SIGINT, SIGTERM),
      3. Call `app.run(host=..., port=..., threaded=True, use_reloader=False)`,
      4. Run `shutdown()` in the finally block on normal Flask return.

    We patch `app.run` to return immediately so the test doesn't hang.
    `pipfile.exists()` after the call confirms `shutdown` removed the pidfile.
    """
    captured: dict = {}

    # Don't actually install global signal handlers — record the calls.
    monkeypatch.setattr("aido.main.signal.signal", MagicMock())

    import aido.main as main_mod

    real_build = main_mod.build_runtime

    def wrapped_build(**kwargs):
        rt: main_mod.RuntimeContext = real_build(**kwargs)
        captured["rt"] = rt
        captured["app_run"] = MagicMock()
        rt.app.run = captured["app_run"]  # type: ignore[attr-defined]
        return rt

    monkeypatch.setattr("aido.main.build_runtime", wrapped_build)

    rt = main_mod.run(
        config_path=cfg_paths["cfg"],
        pidfile=cfg_paths["pidfile"],
        run_web=True,
    )

    # Flask was called with the expected kwargs from the config.
    assert captured["app_run"].called
    call_kwargs = captured["app_run"].call_args.kwargs
    assert call_kwargs["host"] == "127.0.0.1"
    assert call_kwargs["port"] == 0
    assert call_kwargs["threaded"] is True
    assert call_kwargs["use_reloader"] is False

    # Signal handlers were installed for both SIGTERM and SIGINT.
    sig_mock = main_mod.signal.signal
    installed_signals = {call.args[0] for call in sig_mock.call_args_list}
    assert signal.SIGTERM in installed_signals
    assert signal.SIGINT in installed_signals

    # The `finally` block ran shutdown, which releases the pidfile.
    assert not cfg_paths["pidfile"].exists()
    assert rt is captured["rt"]


def test_sigterm_handler_triggers_shutdown_and_sys_exit(cfg_paths, monkeypatch):
    """The locally-scoped `_sigterm` handler in `run` must call
    `rt.shutdown()` and `sys.exit(0)`. We capture the handler that was
    registered and invoke it directly.
    """
    registered: dict = {}

    def fake_signal_signal(sig, handler):
        registered[sig] = handler

    monkeypatch.setattr("aido.main.signal.signal", fake_signal_signal)

    import aido.main as main_mod

    real_build = main_mod.build_runtime
    captured: dict = {}

    def wrapped_build(**kwargs):
        rt: main_mod.RuntimeContext = real_build(**kwargs)
        rt.app.run = MagicMock()  # type: ignore[attr-defined]
        # Wrap shutdown so we can verify it runs from the signal handler.
        original_shutdown = rt.shutdown
        captured["shutdown_calls"] = 0

        def counted_shutdown() -> None:
            captured["shutdown_calls"] += 1
            original_shutdown()

        rt.shutdown = counted_shutdown  # type: ignore[method-assign]
        captured["rt"] = rt
        return rt

    monkeypatch.setattr("aido.main.build_runtime", wrapped_build)

    main_mod.run(
        config_path=cfg_paths["cfg"],
        pidfile=cfg_paths["pidfile"],
        run_web=True,
    )

    # `run` itself called shutdown via the `finally` clause once Flask returned.
    # Now invoke the SIGTERM handler that was registered; it should call
    # shutdown again and then sys.exit.
    handler = registered[signal.SIGTERM]
    with pytest.raises(SystemExit) as ei:
        handler(signal.SIGTERM, None)
    assert ei.value.code == 0
    # shutdown ran at least twice: once from finally, once from the signal handler.
    assert captured["shutdown_calls"] >= 2


def test_main_parses_argv_and_returns_zero(cfg_paths, monkeypatch):
    """`main(argv)` must parse --config / --pidfile and call `run(...)`,
    returning 0.

    `main.py` lines 113-119.
    """
    calls: dict = {}

    def fake_run(**kwargs):
        calls["kwargs"] = kwargs
        return MagicMock()

    monkeypatch.setattr("aido.main.run", fake_run)

    import aido.main as main_mod

    rc = main_mod.main(
        [
            "--config",
            str(cfg_paths["cfg"]),
            "--pidfile",
            str(cfg_paths["pidfile"]),
        ]
    )
    assert rc == 0
    assert calls["kwargs"]["config_path"] == cfg_paths["cfg"]
    assert calls["kwargs"]["pidfile"] == cfg_paths["pidfile"]


def test_main_uses_defaults_when_no_argv(monkeypatch):
    """With no argv, the defaults `/app/config.yaml` and `/var/run/aido.pid`
    are used.
    """
    calls: dict = {}

    def fake_run(**kwargs):
        calls["kwargs"] = kwargs
        return MagicMock()

    monkeypatch.setattr("aido.main.run", fake_run)

    import aido.main as main_mod

    rc = main_mod.main([])
    assert rc == 0
    assert calls["kwargs"]["config_path"] == Path("/app/config.yaml")
    assert calls["kwargs"]["pidfile"] == Path("/var/run/aido.pid")
