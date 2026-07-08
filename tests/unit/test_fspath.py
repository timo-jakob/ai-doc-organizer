from pathlib import Path

import pytest

from aido._fspath import validated_fs_path


def test_returns_resolved_absolute_path(tmp_path: Path):
    raw = tmp_path / "sub" / ".." / "aido.sqlite"
    result = validated_fs_path(raw)
    assert result.is_absolute()
    # `..` is collapsed and the path is canonicalized.
    assert result == (tmp_path / "aido.sqlite").resolve()


def test_accepts_str_input(tmp_path: Path):
    result = validated_fs_path(str(tmp_path / "x.yaml"))
    assert result == (tmp_path / "x.yaml").resolve()


def test_empty_path_raises():
    with pytest.raises(ValueError, match="invalid filesystem path"):
        validated_fs_path("")


def test_nul_byte_raises():
    with pytest.raises(ValueError, match="invalid filesystem path"):
        validated_fs_path("/tmp/evil\x00.txt")
