"""Classifier Protocol and re-export of ClassificationResult."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from aido.types import ClassificationResult

__all__ = ["Classifier", "ClassificationResult"]


@runtime_checkable
class Classifier(Protocol):
    """A classifier takes the extracted text of a document and returns a
    structured `ClassificationResult`. Implementations may raise any exception;
    the worker pipeline (Task 21) is responsible for catching and routing.
    """

    def classify(self, text: str, original_filename: str) -> ClassificationResult: ...
