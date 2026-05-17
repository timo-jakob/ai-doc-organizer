from pathlib import Path

import pytest

from aido.config import (
    ClassifierBackend,
    Config,
    load_config,
)


def _write(p: Path, body: str) -> Path:
    p.write_text(body, encoding="utf-8")
    return p


def test_loads_valid_config(tmp_path: Path):
    cfg_path = _write(tmp_path / "config.yaml", """
archive_root: /archive
scan_inbox: /scans
db_path: /data/aido.sqlite
log_path: /var/log/aido/aido.log

classifier:
  backend: agent_sdk
  model: claude-opus-4-7
  review_confidence_threshold: 0.75

web:
  bind: 0.0.0.0
  port: 8765
""".strip())

    cfg = load_config(cfg_path)
    assert isinstance(cfg, Config)
    assert cfg.archive_root == Path("/archive")
    assert cfg.scan_inbox == Path("/scans")
    assert cfg.classifier.backend == ClassifierBackend.AGENT_SDK
    assert cfg.classifier.model == "claude-opus-4-7"
    assert cfg.classifier.review_confidence_threshold == 0.75
    assert cfg.web.bind == "0.0.0.0"
    assert cfg.web.port == 8765


def test_unknown_backend_raises(tmp_path: Path):
    cfg_path = _write(tmp_path / "config.yaml", """
archive_root: /a
scan_inbox: /s
db_path: /d.sqlite
log_path: /l.log
classifier:
  backend: rocketship
  model: x
  review_confidence_threshold: 0.5
web:
  bind: 0.0.0.0
  port: 8765
""".strip())
    with pytest.raises(ValueError, match="rocketship"):
        load_config(cfg_path)


def test_missing_required_key_raises(tmp_path: Path):
    cfg_path = _write(tmp_path / "config.yaml", "archive_root: /a\n")
    with pytest.raises(ValueError, match="scan_inbox"):
        load_config(cfg_path)


def test_threshold_out_of_range_raises(tmp_path: Path):
    cfg_path = _write(tmp_path / "config.yaml", """
archive_root: /a
scan_inbox: /s
db_path: /d.sqlite
log_path: /l.log
classifier:
  backend: agent_sdk
  model: x
  review_confidence_threshold: 1.5
web:
  bind: 0.0.0.0
  port: 8765
""".strip())
    with pytest.raises(ValueError, match="threshold"):
        load_config(cfg_path)
