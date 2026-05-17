"""Shared pytest fixtures for aido tests."""
from __future__ import annotations

import logging
from pathlib import Path
import pytest


@pytest.fixture(autouse=True)
def _reset_aido_logging():
    """Reset aido logger state between tests to prevent handler leakage.

    The aido logger installs a TimedRotatingFileHandler that points to tmp_path.
    If not reset, subsequent tests inherit a handler pointing to a deleted tmp_path,
    causing FileNotFoundError when they try to log.
    """
    import aido.logging_setup as ls

    # Reset before test
    ls._CONFIGURED = False
    logger = logging.getLogger("aido")
    for h in list(logger.handlers):
        logger.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass

    yield

    # Reset after test
    ls._CONFIGURED = False
    logger = logging.getLogger("aido")
    for h in list(logger.handlers):
        logger.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass


@pytest.fixture
def tmp_archive(tmp_path: Path) -> Path:
    """Empty archive root for a test."""
    root = tmp_path / "archive"
    root.mkdir()
    return root


@pytest.fixture
def tmp_inbox(tmp_path: Path) -> Path:
    """Empty scan inbox for a test."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    return inbox
