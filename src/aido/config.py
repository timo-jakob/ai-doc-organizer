"""YAML config loader for aido."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ruamel.yaml import YAML


class ClassifierBackend(StrEnum):
    AGENT_SDK = "agent_sdk"
    ANTHROPIC_API = "anthropic_api"
    LOCAL_LLM = "local_llm"
    FAKE = "fake"  # for tests


@dataclass(frozen=True, slots=True)
class ClassifierConfig:
    backend: ClassifierBackend
    model: str
    review_confidence_threshold: float


@dataclass(frozen=True, slots=True)
class WebConfig:
    bind: str
    port: int


@dataclass(frozen=True, slots=True)
class Config:
    archive_root: Path
    scan_inbox: Path
    db_path: Path
    log_path: Path
    classifier: ClassifierConfig
    web: WebConfig


def _require(d: dict, key: str) -> object:
    if key not in d:
        raise ValueError(f"Missing required config key: {key}")
    return d[key]


def load_config(path: Path) -> Config:
    yaml = YAML(typ="safe")
    raw = yaml.load(
        path.read_text(encoding="utf-8")
    )  # nosonar pythonsecurity:S8707 — path is supplied by the human operator (daemon config), not derived from LLM output
    if not isinstance(raw, dict):
        raise ValueError(f"{path} is not a YAML mapping")

    # Validate top-level required keys first
    archive_root = Path(str(_require(raw, "archive_root")))
    scan_inbox = Path(str(_require(raw, "scan_inbox")))
    db_path = Path(str(_require(raw, "db_path")))
    log_path = Path(str(_require(raw, "log_path")))

    cls = _require(raw, "classifier")
    if not isinstance(cls, dict):
        raise ValueError("classifier must be a mapping")
    backend_raw = _require(cls, "backend")
    try:
        backend = ClassifierBackend(backend_raw)
    except ValueError as e:
        raise ValueError(f"Unknown classifier backend: {backend_raw!r}") from e
    threshold = float(_require(cls, "review_confidence_threshold"))
    if not (0.0 <= threshold <= 1.0):
        raise ValueError(
            f"classifier.review_confidence_threshold must be in [0, 1] (got {threshold})"
        )

    web = _require(raw, "web")
    if not isinstance(web, dict):
        raise ValueError("web must be a mapping")
    raw_port = _require(web, "port")
    # Coerce to int, but keep the ValueError contract the rest of this loader
    # uses: a null / list / mapping port would make int() raise TypeError, and
    # a YAML bool (int subclass) would sneak `true` -> 1 past the range check.
    if isinstance(raw_port, bool):
        raise ValueError(f"web.port must be an integer (got {raw_port!r})")
    try:
        port = int(raw_port)
    except (TypeError, ValueError) as e:
        raise ValueError(f"web.port must be an integer (got {raw_port!r})") from e
    if not (1 <= port <= 65535):
        raise ValueError(f"web.port must be in [1, 65535] (got {port})")

    return Config(
        archive_root=archive_root,
        scan_inbox=scan_inbox,
        db_path=db_path,
        log_path=log_path,
        classifier=ClassifierConfig(
            backend=backend,
            model=str(_require(cls, "model")),
            review_confidence_threshold=threshold,
        ),
        web=WebConfig(
            bind=str(_require(web, "bind")),
            port=port,
        ),
    )
