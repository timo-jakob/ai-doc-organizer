import asyncio
import json
from datetime import date

import pytest

from aido.classifier.agent_sdk import AgentSDKClassifier, build_system_prompt
from aido.store.connection import connect
from aido.store.migrations import init_db
from aido.store.persons import add_alias, create_person
from aido.store.taxonomy import create_category, create_doctype


@pytest.fixture
def taxonomy_conn(tmp_path):
    with connect(tmp_path / "x.sqlite") as c:
        init_db(c)
        timo = create_person(c, slug="timo", display_name="Timo Jakob")
        anna = create_person(c, slug="anna", display_name="Anna Jakob")
        shared = create_person(c, slug="shared", display_name="Shared", is_shared=True)
        for alias in ("Timo Jakob", "T. Jakob", "Jakob"):
            add_alias(c, person_id=timo.id, alias=alias)
        add_alias(c, person_id=anna.id, alias="Anna Jakob")
        create_category(c, slug="rechnungen", display_name="Rechnungen",
                        description="Eingehende Rechnungen aller Art")
        create_category(c, slug="_review", display_name="_review", is_review=True)
        create_doctype(c, slug="rechnung", display_name="Rechnung",
                       description="Eine Rechnung von einem Anbieter")
        create_doctype(c, slug="letter", display_name="Brief")
        yield c


def test_build_system_prompt_contains_all_taxonomy(taxonomy_conn):
    prompt = build_system_prompt(taxonomy_conn)
    assert "timo" in prompt
    assert "shared" in prompt
    assert "Jakob" in prompt
    assert "rechnungen" in prompt
    assert "rechnung" in prompt
    assert "JSON" in prompt
    assert "_review" not in prompt.split("CATEGORIES:")[1].split("DOCTYPES:")[0]
    # joint-mail rule:
    assert "single family member" in prompt.lower()


def test_classify_parses_valid_json_response(taxonomy_conn, mocker):
    payload = {
        "person_slug": "timo",
        "category_slug": "rechnungen",
        "doctype_slug": "rechnung",
        "document_date": "2026-03-12",
        "counterparty": "Telekom",
        "proposed_filename": "2026-03-12_rechnung_telekom.pdf",
        "overall_confidence": 0.93,
        "person_confidence": 0.95,
        "category_confidence": 0.91,
        "new_category_proposal": None,
        "reasoning": "Recipient Timo Jakob; sender Telekom",
    }
    fake_response_text = (
        "<classification>\n" + json.dumps(payload) + "\n</classification>\n"
    )

    async def fake_query(prompt, options):
        yield _text_block(fake_response_text)

    mocker.patch("aido.classifier.agent_sdk._sdk_query", new=fake_query)

    cls = AgentSDKClassifier(conn=taxonomy_conn, model="claude-opus-4-7")
    result = cls.classify(text="some doc text", original_filename="scan001.pdf")
    assert result.person_slug == "timo"
    assert result.document_date == date(2026, 3, 12)
    assert result.overall_confidence == pytest.approx(0.93)


def test_classify_raises_on_no_classification_tag(taxonomy_conn, mocker):
    async def fake_query(prompt, options):
        yield _text_block("I'm not following the format.")

    mocker.patch("aido.classifier.agent_sdk._sdk_query", new=fake_query)

    cls = AgentSDKClassifier(conn=taxonomy_conn, model="claude-opus-4-7")
    with pytest.raises(ValueError, match="classification"):
        cls.classify(text="x", original_filename="y.pdf")


def _text_block(text: str):
    """Mimics the Agent SDK's text block shape."""
    class _T:
        def __init__(self, t): self.text = t
    class _M:
        def __init__(self, t): self.content = [_T(t)]
    return _M(text)
