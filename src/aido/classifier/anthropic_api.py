"""AnthropicAPIClassifier — opportunistic fallback using direct API key."""
from __future__ import annotations

import logging
import sqlite3

from anthropic import Anthropic

from aido.classifier.agent_sdk import _parse_response, _build_user_prompt, build_system_prompt
from aido.types import ClassificationResult

_log = logging.getLogger("aido.classifier.anthropic_api")


class AnthropicAPIClassifier:
    """Calls Anthropic's Messages API directly with an API key."""

    def __init__(self, conn: sqlite3.Connection, *, model: str, api_key: str) -> None:
        self._conn = conn
        self._model = model
        self._client = Anthropic(api_key=api_key)

    def classify(self, text: str, original_filename: str) -> ClassificationResult:
        system_prompt = build_system_prompt(self._conn)
        user_prompt = _build_user_prompt(text, original_filename)
        response = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_prompt}],
        )
        usage = response.usage
        _log.info(
            "classifier.usage",
            extra={
                "model": response.model,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cache_creation_input_tokens": usage.cache_creation_input_tokens or 0,
                "cache_read_input_tokens": usage.cache_read_input_tokens or 0,
                "stop_reason": response.stop_reason,
            },
        )
        raw = "".join(getattr(b, "text", "") for b in response.content)
        return _parse_response(raw)
