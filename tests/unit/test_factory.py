import pytest

from aido.classifier.agent_sdk import AgentSDKClassifier
from aido.classifier.anthropic_api import AnthropicAPIClassifier
from aido.classifier.factory import build_classifier
from aido.classifier.fake import FakeClassifier
from aido.config import ClassifierBackend, ClassifierConfig
from aido.store.connection import connect
from aido.store.migrations import init_db


@pytest.fixture
def conn(tmp_path):
    with connect(tmp_path / "x.sqlite") as c:
        init_db(c)
        yield c


def test_builds_agent_sdk(conn):
    cfg = ClassifierConfig(
        backend=ClassifierBackend.AGENT_SDK,
        model="claude-opus-4-7",
        review_confidence_threshold=0.75,
    )
    cls = build_classifier(conn, cfg)
    assert isinstance(cls, AgentSDKClassifier)


def test_builds_anthropic_api_requires_key(conn, monkeypatch):
    cfg = ClassifierConfig(
        backend=ClassifierBackend.ANTHROPIC_API,
        model="claude-opus-4-7",
        review_confidence_threshold=0.75,
    )
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        build_classifier(conn, cfg)


def test_builds_anthropic_api_with_key(conn, monkeypatch):
    cfg = ClassifierConfig(
        backend=ClassifierBackend.ANTHROPIC_API,
        model="claude-opus-4-7",
        review_confidence_threshold=0.75,
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    cls = build_classifier(conn, cfg)
    assert isinstance(cls, AnthropicAPIClassifier)


def test_local_llm_not_implemented(conn):
    cfg = ClassifierConfig(
        backend=ClassifierBackend.LOCAL_LLM,
        model="llama3",
        review_confidence_threshold=0.75,
    )
    with pytest.raises(NotImplementedError):
        build_classifier(conn, cfg)


def test_fake_returns_fake_classifier(conn):
    cfg = ClassifierConfig(
        backend=ClassifierBackend.FAKE,
        model="x",
        review_confidence_threshold=0.75,
    )
    cls = build_classifier(conn, cfg)
    assert isinstance(cls, FakeClassifier)
