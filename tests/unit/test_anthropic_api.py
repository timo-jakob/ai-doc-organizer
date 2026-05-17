import json
from datetime import date

import pytest

from aido.classifier.anthropic_api import AnthropicAPIClassifier
from aido.store.connection import connect
from aido.store.migrations import init_db
from aido.store.persons import create_person
from aido.store.taxonomy import create_category, create_doctype


@pytest.fixture
def conn(tmp_path):
    with connect(tmp_path / "x.sqlite") as c:
        init_db(c)
        create_person(c, slug="timo", display_name="Timo Jakob")
        create_category(c, slug="rechnungen", display_name="Rechnungen")
        create_category(c, slug="_review", display_name="_review", is_review=True)
        create_doctype(c, slug="rechnung", display_name="Rechnung")
        yield c


def test_classify_parses_valid_response(conn, mocker):
    payload = {
        "person_slug": "timo",
        "category_slug": "rechnungen",
        "doctype_slug": "rechnung",
        "document_date": "2026-03-12",
        "counterparty": "Telekom",
        "proposed_filename": "2026-03-12_rechnung_telekom.pdf",
        "overall_confidence": 0.9,
        "person_confidence": 0.9,
        "category_confidence": 0.9,
        "new_category_proposal": None,
        "reasoning": "x",
    }
    wrapped = f"<classification>{json.dumps(payload)}</classification>"

    fake_client = mocker.MagicMock()
    fake_response = mocker.MagicMock()
    fake_response.content = [mocker.MagicMock(text=wrapped)]
    fake_client.messages.create.return_value = fake_response
    mocker.patch("aido.classifier.anthropic_api.Anthropic", return_value=fake_client)

    cls = AnthropicAPIClassifier(conn=conn, model="claude-opus-4-7", api_key="x")
    result = cls.classify(text="t", original_filename="f.pdf")
    assert result.person_slug == "timo"
    assert result.document_date == date(2026, 3, 12)
    # Verify cache_control was set on the system block.
    call_kwargs = fake_client.messages.create.call_args.kwargs
    system_blocks = call_kwargs["system"]
    assert isinstance(system_blocks, list)
    assert system_blocks[0]["cache_control"] == {"type": "ephemeral"}
