"""AgentSDKClassifier — v1 default, uses Max Plan via OAuth."""
from __future__ import annotations

import asyncio
import json
import re
import sqlite3
from datetime import date
from typing import AsyncIterator

from claude_agent_sdk import ClaudeAgentOptions, query as _claude_query

from aido.store.persons import list_persons, list_aliases_for
from aido.store.taxonomy import list_categories, list_doctypes
from aido.types import ClassificationResult

_TAG_RE = re.compile(r"<classification>\s*(.*?)\s*</classification>", re.DOTALL)


def build_system_prompt(conn: sqlite3.Connection) -> str:
    """Render the taxonomy from the DB as the static system prompt.

    Identical content across calls so Anthropic's prompt cache applies on
    everything except the per-document user message.
    """
    lines: list[str] = []
    lines.append(
        "You file scanned household documents. Read the document text and decide:\n"
        " - which family member the document is for (the addressee, not the sender),\n"
        " - which category folder the document belongs to,\n"
        " - the document's date (invoice date, letter date, etc.),\n"
        " - the document type (a single label from the doctype vocabulary),\n"
        " - the counterparty (the sender/issuer of the document),\n"
        " - your confidence in each decision (0.0–1.0).\n"
        "\n"
        "If a document is clearly addressed to ONE specific family member, file it "
        "under that person, even when other family members are mentioned. Use the "
        "'shared' person only when no single family member is identifiable (e.g., a "
        "utility bill addressed to the household at large).\n"
        "\n"
        "If you believe a document does not fit any existing category, propose a "
        "new category slug in `new_category_proposal` and pick the closest existing "
        "category as a fallback.\n"
    )
    lines.append("PERSONS:")
    for p in list_persons(conn):
        aliases = [a.alias for a in list_aliases_for(conn, p.id)]
        joined = ", ".join(aliases) if aliases else "(no aliases)"
        marker = " (use for joint/household-only documents)" if p.is_shared else ""
        lines.append(f" - slug: {p.slug}{marker}; display: {p.display_name}; aliases: {joined}")
    lines.append("")
    lines.append("CATEGORIES:")
    for c in list_categories(conn):
        if c.is_review:
            continue  # _review is not an AI-selectable category
        desc = f" — {c.description}" if c.description else ""
        lines.append(f" - {c.slug}{desc}")
    lines.append("")
    lines.append("DOCTYPES:")
    for d in list_doctypes(conn):
        desc = f" — {d.description}" if d.description else ""
        lines.append(f" - {d.slug}{desc}")
    lines.append("")
    lines.append(
        "Respond with EXACTLY one XML tag named `classification` containing JSON "
        "with these keys: person_slug, category_slug, doctype_slug, document_date "
        "(YYYY-MM-DD), counterparty, proposed_filename (YYYY-MM-DD_<doctype>_<party>.pdf, "
        "ASCII only), overall_confidence, person_confidence, category_confidence, "
        "new_category_proposal (string or null), reasoning (one sentence).\n"
        "Do not include any other text outside the tag."
    )
    return "\n".join(lines)


def _build_user_prompt(text: str, original_filename: str) -> str:
    return (
        f"Original filename: {original_filename}\n"
        f"--- DOCUMENT TEXT (truncated) ---\n{text}\n--- END ---"
    )


def _parse_response(raw: str) -> ClassificationResult:
    match = _TAG_RE.search(raw)
    if not match:
        raise ValueError("Response missing <classification>...</classification> tag")
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in <classification>: {e}") from e
    try:
        return ClassificationResult(
            person_slug=str(data["person_slug"]),
            category_slug=str(data["category_slug"]),
            doctype_slug=str(data["doctype_slug"]),
            document_date=date.fromisoformat(str(data["document_date"])),
            counterparty=str(data.get("counterparty") or ""),
            proposed_filename=str(data["proposed_filename"]),
            overall_confidence=float(data["overall_confidence"]),
            person_confidence=float(data["person_confidence"]),
            category_confidence=float(data["category_confidence"]),
            new_category_proposal=(
                str(data["new_category_proposal"])
                if data.get("new_category_proposal")
                else None
            ),
            reasoning=str(data.get("reasoning") or ""),
        )
    except (KeyError, ValueError, TypeError) as e:
        raise ValueError(f"Classification response missing/invalid field: {e}") from e


# Indirection so tests can monkey-patch the SDK call cleanly.
async def _sdk_query(prompt: str, options: ClaudeAgentOptions) -> AsyncIterator:
    async for message in _claude_query(prompt=prompt, options=options):
        yield message


class AgentSDKClassifier:
    """Uses claude-agent-sdk; authenticates via the user's Max Plan OAuth token
    (read by the bundled Claude Code CLI from `$CLAUDE_CONFIG_DIR`)."""

    def __init__(self, conn: sqlite3.Connection, *, model: str) -> None:
        self._conn = conn
        self._model = model

    def classify(self, text: str, original_filename: str) -> ClassificationResult:
        system_prompt = build_system_prompt(self._conn)
        user_prompt = _build_user_prompt(text, original_filename)
        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            model=self._model,
        )
        raw = asyncio.run(self._collect(user_prompt, options))
        return _parse_response(raw)

    @staticmethod
    async def _collect(prompt: str, options: ClaudeAgentOptions) -> str:
        chunks: list[str] = []
        async for message in _sdk_query(prompt, options):
            content = getattr(message, "content", None) or []
            for block in content:
                text = getattr(block, "text", None)
                if text:
                    chunks.append(text)
        return "".join(chunks)
