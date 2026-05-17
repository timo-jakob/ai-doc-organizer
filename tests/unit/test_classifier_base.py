from datetime import date

import pytest

from aido.classifier.base import Classifier
from aido.classifier.fake import FakeClassifier
from aido.types import ClassificationResult


def _sample_result() -> ClassificationResult:
    return ClassificationResult(
        person_slug="timo",
        category_slug="rechnungen",
        doctype_slug="rechnung",
        document_date=date(2026, 3, 12),
        counterparty="telekom",
        proposed_filename="2026-03-12_rechnung_telekom.pdf",
        overall_confidence=0.93,
        person_confidence=0.95,
        category_confidence=0.91,
        new_category_proposal=None,
        reasoning="recipient Timo",
    )


def test_fake_returns_scripted_result():
    fake = FakeClassifier(results=[_sample_result()])
    out = fake.classify(text="ignored", original_filename="scan001.pdf")
    assert out.person_slug == "timo"


def test_fake_records_calls():
    fake = FakeClassifier(results=[_sample_result()])
    fake.classify(text="some text", original_filename="x.pdf")
    assert fake.calls == [("some text", "x.pdf")]


def test_fake_raises_when_results_exhausted():
    fake = FakeClassifier(results=[_sample_result()])
    fake.classify(text="t", original_filename="a.pdf")
    with pytest.raises(AssertionError):
        fake.classify(text="t", original_filename="b.pdf")


def test_fake_can_raise_scripted_error():
    fake = FakeClassifier(results=[RuntimeError("boom")])
    with pytest.raises(RuntimeError, match="boom"):
        fake.classify(text="t", original_filename="a.pdf")


def test_fake_is_a_classifier():
    fake = FakeClassifier(results=[_sample_result()])
    # Duck-typed Protocol check — relying on attribute presence.
    assert isinstance(fake, Classifier)
