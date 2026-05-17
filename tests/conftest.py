"""Shared pytest fixtures for aido tests."""
from __future__ import annotations

from pathlib import Path
import pytest


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
