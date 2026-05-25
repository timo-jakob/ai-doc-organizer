import json
import logging
from pathlib import Path

from aido.logging_setup import JsonFormatter, configure_logging


def test_json_formatter_emits_required_fields():
    record = logging.LogRecord(
        name="aido.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    line = JsonFormatter().format(record)
    obj = json.loads(line)
    assert obj["msg"] == "hello"
    assert obj["level"] == "INFO"
    assert obj["logger"] == "aido.test"
    assert "ts" in obj


def test_json_formatter_includes_extras():
    record = logging.LogRecord(
        name="aido.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    record.source_hash = "abc"
    record.decision_id = 42
    obj = json.loads(JsonFormatter().format(record))
    assert obj["source_hash"] == "abc"
    assert obj["decision_id"] == 42


def test_json_formatter_handles_exc_info():
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            name="aido.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="oops",
            args=(),
            exc_info=True,
        )
        import sys

        record.exc_info = sys.exc_info()
    obj = json.loads(JsonFormatter().format(record))
    assert "exc" in obj
    assert "ValueError" in obj["exc"]


def test_configure_logging_writes_to_file(tmp_path: Path):
    log_path = tmp_path / "subdir" / "aido.log"
    logger = configure_logging(log_path)
    logger.info("hi there", extra={"source_hash": "h1"})
    for h in logger.handlers:
        h.flush()
    text = log_path.read_text(encoding="utf-8")
    line = text.strip().splitlines()[-1]
    obj = json.loads(line)
    assert obj["msg"] == "hi there"
    assert obj["source_hash"] == "h1"
