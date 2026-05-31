"""Behavior tests for `aido.daemon` internals not covered by lifecycle tests.

- `HealthState.record_outcome` failure path + recovery from DEGRADED.
- `HealthState.set` is an explicit override.
- Pidfile acquisition handles corrupt PIDs and live-PID collisions.
- `_process_alive` returns the right thing for unknown / permission-denied PIDs.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from aido.classifier.fake import FakeClassifier
from aido.daemon import Daemon, HealthState, HealthStatus, _process_alive
from aido.worker.pipeline import PipelineOutcome

# ----------------------------------------------------------------------
# HealthState
# ----------------------------------------------------------------------


def _now() -> datetime:
    return datetime(2026, 5, 17, 10, tzinfo=UTC)


def test_health_three_consecutive_failures_marks_degraded() -> None:
    """Three FAILED outcomes in a row must flip status to DEGRADED.

    `daemon.py` lines 48-51: the FAILED branch + threshold check.
    """
    h = HealthState()
    h.record_outcome(PipelineOutcome.FAILED, now=_now())
    assert h.status is HealthStatus.OK
    assert h.consecutive_failures == 1

    h.record_outcome(PipelineOutcome.FAILED, now=_now())
    assert h.status is HealthStatus.OK
    assert h.consecutive_failures == 2

    h.record_outcome(PipelineOutcome.FAILED, now=_now())
    assert h.status is HealthStatus.DEGRADED
    assert h.consecutive_failures == 3


def test_health_success_after_degraded_recovers_to_ok() -> None:
    """A successful outcome after DEGRADED must reset failures and flip to OK.

    `daemon.py` lines 46-47: `if self.status == HealthStatus.DEGRADED: self.status = OK`.
    """
    h = HealthState(status=HealthStatus.DEGRADED, consecutive_failures=5)
    h.record_outcome(PipelineOutcome.AUTO_FILED, now=_now())

    assert h.status is HealthStatus.OK
    assert h.consecutive_failures == 0
    assert h.last_classification_at == _now()


def test_health_review_outcome_also_recovers_from_degraded() -> None:
    """REVIEW counts as a successful classification (no exception)."""
    h = HealthState(status=HealthStatus.DEGRADED, consecutive_failures=3)
    h.record_outcome(PipelineOutcome.REVIEW, now=_now())
    assert h.status is HealthStatus.OK
    assert h.consecutive_failures == 0


def test_health_duplicate_skip_does_not_clear_failures() -> None:
    """DUPLICATE_SKIP is neither a success nor a failure → no state change.

    Confirms `record_outcome` only touches state for AUTO_FILED/REVIEW/FAILED.
    """
    h = HealthState(status=HealthStatus.DEGRADED, consecutive_failures=4)
    h.record_outcome(PipelineOutcome.DUPLICATE_SKIP, now=_now())
    assert h.status is HealthStatus.DEGRADED
    assert h.consecutive_failures == 4
    assert h.last_classification_at is None


def test_health_set_overrides_status() -> None:
    """`HealthState.set` is the explicit override path used by callers.

    `daemon.py` lines 53-55.
    """
    h = HealthState()
    h.set(HealthStatus.AUTH_FAILED)
    assert h.status is HealthStatus.AUTH_FAILED

    h.set(HealthStatus.CANNOT_WRITE)
    assert h.status is HealthStatus.CANNOT_WRITE


# ----------------------------------------------------------------------
# _process_alive
# ----------------------------------------------------------------------


def test_process_alive_true_for_current_process() -> None:
    """Sending signal 0 to our own PID must succeed → True."""
    assert _process_alive(os.getpid()) is True


def test_process_alive_false_for_missing_process() -> None:
    """ProcessLookupError → False.

    `daemon.py` line 174.
    """
    with patch("aido.daemon.os.kill", side_effect=ProcessLookupError):
        assert _process_alive(999_999) is False


def test_process_alive_true_when_permission_denied() -> None:
    """PermissionError means the PID exists but we can't signal it → True.

    `daemon.py` lines 175-176. Important: we MUST NOT treat
    PermissionError as 'dead' or the daemon would happily double-start.
    """
    with patch("aido.daemon.os.kill", side_effect=PermissionError):
        assert _process_alive(1) is True


# ----------------------------------------------------------------------
# Daemon pidfile handling
# ----------------------------------------------------------------------


def _make_daemon(*, db_path: Path, archive: Path, inbox: Path, pidfile: Path) -> Daemon:
    return Daemon(
        db_path=db_path,
        archive_root=archive,
        inbox=inbox,
        classifier_factory=lambda conn: FakeClassifier(results=[]),
        threshold=0.75,
        classifier_model="claude-opus-4-7",
        pidfile=pidfile,
        poll_interval=0.5,
        stabilize_seconds=0.0,
    )


def test_acquire_pidfile_overwrites_corrupt_pidfile(tmp_path: Path) -> None:
    """A pidfile whose content isn't an int must NOT block startup.

    `daemon.py` lines 98-99: `except ValueError: pid = -1`. Then because
    `pid > 0` is False, we fall through and overwrite with our own PID.
    """
    archive = tmp_path / "archive"
    inbox = tmp_path / "inbox"
    archive.mkdir()
    inbox.mkdir()
    pidfile = tmp_path / "aido.pid"
    pidfile.write_text("not-a-number")

    daemon = _make_daemon(
        db_path=tmp_path / "x.sqlite",
        archive=archive,
        inbox=inbox,
        pidfile=pidfile,
    )

    # We don't actually need the whole daemon — just acquire the pidfile.
    daemon._acquire_pidfile()
    try:
        assert pidfile.exists()
        assert pidfile.read_text() == str(os.getpid())
    finally:
        daemon._release_pidfile()
    assert not pidfile.exists()


def test_acquire_pidfile_overwrites_stale_pidfile(tmp_path: Path) -> None:
    """A pidfile pointing at a dead process must NOT block startup.

    `daemon.py` lines 100-103: alive=False path → fall through to overwrite.
    """
    archive = tmp_path / "archive"
    inbox = tmp_path / "inbox"
    archive.mkdir()
    inbox.mkdir()
    pidfile = tmp_path / "aido.pid"
    pidfile.write_text("999999")  # almost certainly dead

    daemon = _make_daemon(
        db_path=tmp_path / "x.sqlite",
        archive=archive,
        inbox=inbox,
        pidfile=pidfile,
    )

    with patch("aido.daemon._process_alive", return_value=False):
        daemon._acquire_pidfile()
    try:
        assert pidfile.read_text() == str(os.getpid())
    finally:
        daemon._release_pidfile()


def test_acquire_pidfile_raises_when_live_process_owns_pidfile(tmp_path: Path) -> None:
    """A pidfile with a LIVE PID must raise to prevent double-start.

    `daemon.py` line 101: `raise RuntimeError(f"aido already running ...")`.
    """
    archive = tmp_path / "archive"
    inbox = tmp_path / "inbox"
    archive.mkdir()
    inbox.mkdir()
    pidfile = tmp_path / "aido.pid"
    pidfile.write_text("12345")

    daemon = _make_daemon(
        db_path=tmp_path / "x.sqlite",
        archive=archive,
        inbox=inbox,
        pidfile=pidfile,
    )

    with (
        patch("aido.daemon._process_alive", return_value=True),
        pytest.raises(RuntimeError, match="already running"),
    ):
        daemon._acquire_pidfile()
    # The original pidfile contents must remain untouched.
    assert pidfile.read_text() == "12345"


def test_release_pidfile_is_idempotent(tmp_path: Path) -> None:
    """Calling `_release_pidfile` twice must not raise."""
    archive = tmp_path / "archive"
    inbox = tmp_path / "inbox"
    archive.mkdir()
    inbox.mkdir()
    pidfile = tmp_path / "aido.pid"

    daemon = _make_daemon(
        db_path=tmp_path / "x.sqlite",
        archive=archive,
        inbox=inbox,
        pidfile=pidfile,
    )
    daemon._acquire_pidfile()
    daemon._release_pidfile()
    daemon._release_pidfile()  # second call must be a no-op
    assert not pidfile.exists()
