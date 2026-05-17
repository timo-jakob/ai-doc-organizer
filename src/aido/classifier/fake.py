"""A scriptable Classifier double for tests."""
from __future__ import annotations

from typing import Sequence

from aido.types import ClassificationResult


class FakeClassifier:
    """Returns scripted results in order. If an item is an Exception subclass
    (or instance), it is raised instead of returned.
    """

    def __init__(self, results: Sequence[ClassificationResult | BaseException]) -> None:
        self._results: list[ClassificationResult | BaseException] = list(results)
        self.calls: list[tuple[str, str]] = []

    def classify(self, text: str, original_filename: str) -> ClassificationResult:
        self.calls.append((text, original_filename))
        assert self._results, "FakeClassifier results exhausted"
        item = self._results.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item
