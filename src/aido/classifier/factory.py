"""Pick a concrete Classifier implementation given config."""
from __future__ import annotations

import os
import sqlite3

from aido.classifier.agent_sdk import AgentSDKClassifier
from aido.classifier.anthropic_api import AnthropicAPIClassifier
from aido.classifier.base import Classifier
from aido.classifier.fake import FakeClassifier
from aido.config import ClassifierBackend, ClassifierConfig


def build_classifier(conn: sqlite3.Connection, cfg: ClassifierConfig) -> Classifier:
    match cfg.backend:
        case ClassifierBackend.AGENT_SDK:
            return AgentSDKClassifier(conn=conn, model=cfg.model)
        case ClassifierBackend.ANTHROPIC_API:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "classifier.backend=anthropic_api requires ANTHROPIC_API_KEY"
                )
            return AnthropicAPIClassifier(conn=conn, model=cfg.model, api_key=api_key)
        case ClassifierBackend.LOCAL_LLM:
            raise NotImplementedError(
                "local_llm backend is post-MVP (Mac mini phase); see spec §12"
            )
        case ClassifierBackend.FAKE:
            return FakeClassifier(results=[])
