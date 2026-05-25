"""Structured JSON logger + RotatingFileHandler."""

from __future__ import annotations

import json
import logging
import logging.handlers
from datetime import UTC, datetime
from pathlib import Path

_BUILTIN = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "asctime",
    "message",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    """Formats a `LogRecord` as a single JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _BUILTIN or key.startswith("_"):
                continue
            out[key] = value
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)


_CONFIGURED = False


def configure_logging(log_path: Path) -> logging.Logger:
    """Install one rotating file handler on the 'aido' logger. Idempotent."""
    global _CONFIGURED
    logger = logging.getLogger("aido")
    if _CONFIGURED:
        return logger
    logger.setLevel(logging.INFO)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.TimedRotatingFileHandler(
        log_path, when="W0", backupCount=8, encoding="utf-8"
    )
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    _CONFIGURED = True
    return logger
