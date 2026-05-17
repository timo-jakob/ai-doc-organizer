# ai-doc-organizer v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `aido` v1: a Dockerised Python service that watches a scanner inbox, classifies each PDF via Claude (Agent SDK + Max Plan), files it into `<archive>/<person>/<category>/YYYY-MM-DD_<doctype>_<counterparty>.pdf`, and exposes a LAN web UI for retrospective audit.

**Architecture:** Single Python process inside one Docker container hosts a `watchdog` file watcher, a single-threaded worker pipeline, a Flask web UI, and a SQLite database. The classifier sits behind a `Classifier` Protocol with `AgentSDKClassifier` (default), `AnthropicAPIClassifier` (fallback), and a `FakeClassifier` for tests. The web UI never writes the DB directly — every mutation goes through an in-process `aido.mutations` API guarded by a `threading.Lock` so the worker thread and HTTP handlers cannot race.

**Tech Stack:** Python 3.13, SQLite (STRICT tables, WAL), Flask + Jinja2 + vanilla JS, `pypdf`, `watchdog` (PollingObserver), `claude-agent-sdk`, `anthropic`, `ruamel.yaml`, `pytest` + `fpdf2` (for synthesised fixture PDFs). Packaged as Docker Compose. Host: macOS on Apple Silicon (MacBook Pro now, Mac mini later).

**Spec:** [`docs/superpowers/specs/2026-05-17-ai-doc-organizer-design.md`](../specs/2026-05-17-ai-doc-organizer-design.md)

---

## Resolved implementation questions (from spec §13)

1. **PDF preview** — `<iframe>` serving raw bytes via Flask. Simpler, no extra deps.
2. **Mutation transport** — In-process function calls. Flask handlers call `aido.mutations.*` directly under a `threading.Lock`.
3. **`aido init`** — Hybrid: `--seed seed.yaml` for non-interactive (tests + automation); otherwise interactive prompts.
4. **Agent SDK structured output** — JSON-in-system-prompt + parse for v1. Refactor target if/when the SDK's tool-use bindings stabilise.
5. **OAuth credentials volume** — Read-write. Claude Code CLI may rotate tokens; read-only would break silently.

---

## File structure

Reference map. Each path is created by a specific task below.

```
ai-doc-organizer/
├── docker-compose.yml                # Task 30
├── Dockerfile                        # Task 30
├── .dockerignore                     # Task 30
├── pyproject.toml                    # Task 0
├── config.example.yaml               # Task 15
├── README.md                         # Task 33
├── src/aido/
│   ├── __init__.py                   # Task 0
│   ├── __main__.py                   # Task 27 (CLI entrypoint)
│   ├── types.py                      # Task 1  (enums + dataclasses)
│   ├── config.py                     # Task 15 (YAML config loader)
│   ├── logging_setup.py              # Task 16 (JSON logger + rotation)
│   ├── filing/
│   │   ├── __init__.py
│   │   ├── alias.py                  # Task 2  (slug + alias normalisation)
│   │   ├── filename.py               # Task 3  (filename builder)
│   │   └── executor.py               # Task 13 (atomic move + collision)
│   ├── pdf/
│   │   ├── __init__.py
│   │   ├── hash.py                   # Task 4  (sha256_of_file)
│   │   └── extract.py                # Task 5  (pypdf text extraction)
│   ├── store/
│   │   ├── __init__.py
│   │   ├── schema.sql                # Task 6  (DDL)
│   │   ├── connection.py             # Task 6  (connect + pragmas + adapters)
│   │   ├── migrations.py             # Task 6  (run schema if empty)
│   │   ├── persons.py                # Task 7  (persons + aliases CRUD)
│   │   ├── taxonomy.py               # Task 8  (categories + doctypes CRUD)
│   │   ├── decisions.py              # Task 9  (decisions CRUD + queries)
│   │   ├── manual_actions.py         # Task 10 (audit rows)
│   │   └── pending_jobs.py           # Task 10 (retry queue)
│   ├── classifier/
│   │   ├── __init__.py
│   │   ├── base.py                   # Task 11 (Protocol + ClassificationResult)
│   │   ├── fake.py                   # Task 11 (FakeClassifier for tests)
│   │   ├── routing.py                # Task 12 (slug resolution + route decision)
│   │   ├── agent_sdk.py              # Task 17 (AgentSDKClassifier)
│   │   ├── anthropic_api.py          # Task 18 (AnthropicAPIClassifier)
│   │   └── factory.py                # Task 19 (build_classifier from config)
│   ├── worker/
│   │   ├── __init__.py
│   │   ├── queue.py                  # Task 20 (thread-safe inbox queue)
│   │   ├── pipeline.py               # Task 21 (process_one_document)
│   │   └── watcher.py                # Task 22 (PollingObserver wrapper)
│   ├── mutations.py                  # Task 14 (re_file/rename/delete/approve/promote_category)
│   ├── daemon.py                     # Task 23 (lifecycle, healthz state, pidfile)
│   ├── cli.py                        # Task 24 (aido init / status / rebuild-index)
│   └── webui/
│       ├── __init__.py
│       ├── app.py                    # Task 25 (Flask factory)
│       ├── routes.py                 # Task 26 (feed/detail/healthz)
│       ├── mutation_routes.py        # Task 28 (POST endpoints → mutations.*)
│       ├── settings_routes.py        # Task 29 (taxonomy/persons admin)
│       ├── static/app.js             # Task 26
│       └── templates/
│           ├── base.html             # Task 25
│           ├── feed.html             # Task 26
│           ├── detail.html           # Task 27
│           ├── settings.html         # Task 29
│           └── stats.html            # Task 27
└── tests/
    ├── conftest.py                   # Task 0  (shared fixtures: tmp DB, PDFs, etc.)
    ├── fixtures.py                   # Task 4  (synth_pdf() helper using fpdf2)
    ├── unit/
    │   ├── test_types.py             # Task 1
    │   ├── test_alias.py             # Task 2
    │   ├── test_filename.py          # Task 3
    │   ├── test_pdf_hash.py          # Task 4
    │   ├── test_pdf_extract.py       # Task 5
    │   ├── test_store_connection.py  # Task 6
    │   ├── test_store_persons.py     # Task 7
    │   ├── test_store_taxonomy.py    # Task 8
    │   ├── test_store_decisions.py   # Task 9
    │   ├── test_store_pending.py     # Task 10
    │   ├── test_classifier_base.py   # Task 11
    │   ├── test_routing.py           # Task 12
    │   ├── test_filing_executor.py   # Task 13
    │   ├── test_mutations.py         # Task 14
    │   ├── test_config.py            # Task 15
    │   ├── test_logging.py           # Task 16
    │   ├── test_agent_sdk.py         # Task 17
    │   ├── test_anthropic_api.py     # Task 18
    │   ├── test_factory.py           # Task 19
    │   ├── test_queue.py             # Task 20
    │   └── test_pipeline.py          # Task 21
    ├── integration/
    │   ├── test_watcher.py           # Task 22
    │   ├── test_daemon_lifecycle.py  # Task 23
    │   ├── test_cli_init.py          # Task 24
    │   ├── test_webui_feed.py        # Task 26
    │   ├── test_webui_detail.py      # Task 27
    │   ├── test_webui_mutations.py   # Task 28
    │   ├── test_webui_settings.py    # Task 29
    │   └── test_e2e.py               # Task 31
    └── manual/
        └── runbook.md                # Task 32
```

---

## Task 0: Project bootstrap (pyproject, package skeleton, conftest)

**Files:**
- Create: `pyproject.toml`
- Create: `src/aido/__init__.py`
- Create: `src/aido/filing/__init__.py`
- Create: `src/aido/pdf/__init__.py`
- Create: `src/aido/store/__init__.py`
- Create: `src/aido/classifier/__init__.py`
- Create: `src/aido/worker/__init__.py`
- Create: `src/aido/webui/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/integration/__init__.py`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "aido"
version = "0.1.0"
description = "Household document auto-filer for Claude"
requires-python = ">=3.13"
dependencies = [
    "claude-agent-sdk>=0.1.0",
    "anthropic>=0.40.0",
    "pypdf>=4.0.0",
    "watchdog>=4.0.0",
    "flask>=3.0.0",
    "jinja2>=3.1.0",
    "ruamel.yaml>=0.18.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-mock>=3.12.0",
    "fpdf2>=2.7.0",
]

[project.scripts]
aido = "aido.cli:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers"
```

- [ ] **Step 2: Create empty `__init__.py` files for every package**

Each of `src/aido/__init__.py`, `src/aido/filing/__init__.py`, `src/aido/pdf/__init__.py`, `src/aido/store/__init__.py`, `src/aido/classifier/__init__.py`, `src/aido/worker/__init__.py`, `src/aido/webui/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py` is an empty file (single newline).

- [ ] **Step 3: Write minimal `tests/conftest.py`**

```python
"""Shared pytest fixtures for aido tests."""
from __future__ import annotations

from pathlib import Path
import pytest


@pytest.fixture
def tmp_archive(tmp_path: Path) -> Path:
    """Empty archive root for a test."""
    root = tmp_path / "archive"
    root.mkdir()
    return root


@pytest.fixture
def tmp_inbox(tmp_path: Path) -> Path:
    """Empty scan inbox for a test."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    return inbox
```

- [ ] **Step 4: Install dev dependencies and run pytest**

Run:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -v
```
Expected: `no tests ran` (or 0 collected) — confirms install + pytest discovery work.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/ tests/
git commit -m "chore: bootstrap aido package skeleton + pytest config"
```

---

## Task 1: Domain types and enums

**Files:**
- Create: `src/aido/types.py`
- Test: `tests/unit/test_types.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_types.py
from datetime import date, datetime

import pytest

from aido.types import (
    ClassificationResult,
    DecisionStatus,
    ManualAction,
    RouteOutcome,
)


def test_decision_status_values():
    assert DecisionStatus.AUTO_FILED.value == "auto_filed"
    assert DecisionStatus.REVIEW.value == "review"
    assert DecisionStatus.HUMAN_FILED.value == "human_filed"
    assert DecisionStatus.FAILED.value == "failed"


def test_manual_action_values():
    assert ManualAction.RE_FILE.value == "re_file"
    assert ManualAction.RENAME.value == "rename"
    assert ManualAction.DELETE.value == "delete"
    assert ManualAction.APPROVE.value == "approve"
    assert ManualAction.PROMOTE_CATEGORY.value == "promote_category"


def test_decision_status_is_str_enum():
    assert isinstance(DecisionStatus.AUTO_FILED, str)
    assert DecisionStatus.AUTO_FILED == "auto_filed"


def test_classification_result_constructs():
    r = ClassificationResult(
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
        reasoning="Recipient 'Timo Jakob'; sender Telekom; invoice format.",
    )
    assert r.person_slug == "timo"
    assert r.document_date == date(2026, 3, 12)
    assert r.new_category_proposal is None


def test_classification_result_rejects_invalid_confidence():
    with pytest.raises(ValueError):
        ClassificationResult(
            person_slug="timo",
            category_slug="rechnungen",
            doctype_slug="rechnung",
            document_date=date(2026, 3, 12),
            counterparty="telekom",
            proposed_filename="x.pdf",
            overall_confidence=1.5,  # invalid
            person_confidence=0.9,
            category_confidence=0.9,
            new_category_proposal=None,
            reasoning="",
        )


def test_route_outcome_enum():
    assert RouteOutcome.AUTO_FILE.value == "auto_file"
    assert RouteOutcome.REVIEW.value == "review"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_types.py -v`
Expected: `ImportError: No module named 'aido.types'`.

- [ ] **Step 3: Write `src/aido/types.py`**

```python
"""Domain types and enums for aido."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class DecisionStatus(str, Enum):
    AUTO_FILED = "auto_filed"
    REVIEW = "review"
    HUMAN_FILED = "human_filed"
    FAILED = "failed"


class ManualAction(str, Enum):
    RE_FILE = "re_file"
    RENAME = "rename"
    DELETE = "delete"
    APPROVE = "approve"
    PROMOTE_CATEGORY = "promote_category"


class RouteOutcome(str, Enum):
    AUTO_FILE = "auto_file"
    REVIEW = "review"


def _check_confidence(name: str, value: float) -> None:
    if not (0.0 <= value <= 1.0):
        raise ValueError(f"{name} must be in [0, 1], got {value!r}")


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    """Output of a Classifier.classify() call.

    The classifier returns slugs, not IDs. Slug → ID resolution is done by
    aido.classifier.routing (see Task 12).
    """

    person_slug: str
    category_slug: str
    doctype_slug: str
    document_date: date
    counterparty: str
    proposed_filename: str
    overall_confidence: float
    person_confidence: float
    category_confidence: float
    new_category_proposal: str | None
    reasoning: str

    def __post_init__(self) -> None:
        _check_confidence("overall_confidence", self.overall_confidence)
        _check_confidence("person_confidence", self.person_confidence)
        _check_confidence("category_confidence", self.category_confidence)
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/unit/test_types.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/aido/types.py tests/unit/test_types.py
git commit -m "feat(types): add DecisionStatus, ManualAction, ClassificationResult"
```

---

## Task 2: Slug + alias normalisation

**Files:**
- Create: `src/aido/filing/alias.py`
- Test: `tests/unit/test_alias.py`

`alias_normalize()` turns a name like `"Penélope Müller"` into `"penelope mueller"` so the DB can use a deterministic key. `slugify()` produces filesystem-safe slugs for paths (`"Penélope" → "penelope"`, `"Stadt München" → "stadt-muenchen"`).

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_alias.py
import pytest

from aido.filing.alias import alias_normalize, slugify


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Jakob", "jakob"),
        ("Jacob", "jacob"),
        ("Penélope", "penelope"),
        ("Penelope", "penelope"),
        ("Pénélope Müller", "penelope mueller"),
        ("Timo Jakob", "timo jakob"),
        ("  T.  Jakob ", "t. jakob"),
        ("Straße", "strasse"),
        ("Ärger", "aerger"),
        ("Œuvre", "oeuvre"),
        ("", ""),
    ],
)
def test_alias_normalize(raw: str, expected: str) -> None:
    assert alias_normalize(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Telekom", "telekom"),
        ("Stadt München", "stadt-muenchen"),
        ("E.ON Energie", "e-on-energie"),
        ("DKB AG", "dkb-ag"),
        ("  multi   spaces  ", "multi-spaces"),
        ("--leading-and-trailing--", "leading-and-trailing"),
        ("café-é-è", "cafe-e-e"),
        ("", ""),
        ("???", ""),
    ],
)
def test_slugify(raw: str, expected: str) -> None:
    assert slugify(raw) == expected


def test_slugify_truncates_to_length():
    long = "a" * 200
    assert len(slugify(long, max_length=50)) == 50
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/unit/test_alias.py -v`
Expected: import error / module missing.

- [ ] **Step 3: Implement `src/aido/filing/alias.py`**

```python
"""Name and slug normalisation utilities.

`alias_normalize` produces a lowercased, accent-stripped key suitable for the
`person_aliases.alias_normalized` UNIQUE column. `slugify` produces a
filesystem-safe slug (lowercased, hyphen-separated, ASCII-only) used in
filenames and folder paths.
"""
from __future__ import annotations

import re
import unicodedata

_GERMAN_MAP = {
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "Ä": "ae", "Ö": "oe", "Ü": "ue",
    "œ": "oe", "Œ": "oe",
    "æ": "ae", "Æ": "ae",
}


def _transliterate(text: str) -> str:
    """Replace German + Latin ligatures, then strip remaining diacritics."""
    out = []
    for ch in text:
        if ch in _GERMAN_MAP:
            out.append(_GERMAN_MAP[ch])
        else:
            out.append(ch)
    s = "".join(out)
    # NFKD splits accented letters into base + combining mark; we drop the mark.
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def alias_normalize(name: str) -> str:
    """Normalise a person name for storage in `alias_normalized`.

    Lowercases, transliterates German/Latin special chars, collapses internal
    whitespace, strips leading/trailing whitespace. Keeps `.` so initials
    survive (e.g., 't. jakob').
    """
    s = _transliterate(name).lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s


def slugify(text: str, *, max_length: int = 80) -> str:
    """Produce a filesystem-safe slug.

    Lowercase, ASCII-only via transliteration, non-alphanum/hyphen chars
    collapsed to single hyphens, leading/trailing hyphens stripped, truncated
    to `max_length`.
    """
    s = _transliterate(text).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    if len(s) > max_length:
        s = s[:max_length].rstrip("-")
    return s
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/unit/test_alias.py -v`
Expected: 14 passed.

- [ ] **Step 5: Commit**

```bash
git add src/aido/filing/alias.py tests/unit/test_alias.py
git commit -m "feat(filing): add alias_normalize and slugify"
```

---

## Task 3: Filename builder

**Files:**
- Create: `src/aido/filing/filename.py`
- Test: `tests/unit/test_filename.py`

Builds `YYYY-MM-DD_<doctype>_<counterparty>.pdf` with collision-aware suffixing. Doctype + counterparty are pre-slugged by `slugify`. Length cap ~80 chars on the stem; collisions append `_2`, `_3`, ...

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_filename.py
from datetime import date
from pathlib import Path

import pytest

from aido.filing.filename import build_filename, next_available_name


def test_build_basic():
    name = build_filename(date(2026, 3, 12), "rechnung", "telekom")
    assert name == "2026-03-12_rechnung_telekom.pdf"


def test_build_with_special_chars():
    name = build_filename(date(2026, 2, 8), "tax-notice", "Finanzamt München")
    assert name == "2026-02-08_tax-notice_finanzamt-muenchen.pdf"


def test_build_empty_counterparty_falls_back_to_unknown():
    name = build_filename(date(2026, 3, 1), "letter", "")
    assert name == "2026-03-01_letter_unknown.pdf"


def test_build_empty_doctype_falls_back_to_letter():
    name = build_filename(date(2026, 3, 1), "", "telekom")
    assert name == "2026-03-01_letter_telekom.pdf"


def test_build_truncates_when_too_long():
    long_party = "a" * 200
    name = build_filename(date(2026, 3, 1), "rechnung", long_party)
    # YYYY-MM-DD_ + 'rechnung_' + slugged party + '.pdf', total <= 80 + '.pdf'
    stem, ext = name.rsplit(".", 1)
    assert ext == "pdf"
    assert len(stem) <= 80


def test_next_available_name_no_collision(tmp_path: Path):
    target = tmp_path / "2026-03-12_rechnung_telekom.pdf"
    assert next_available_name(target) == target


def test_next_available_name_one_collision(tmp_path: Path):
    base = tmp_path / "2026-03-12_rechnung_telekom.pdf"
    base.touch()
    assert next_available_name(base) == tmp_path / "2026-03-12_rechnung_telekom_2.pdf"


def test_next_available_name_multiple_collisions(tmp_path: Path):
    for i in (None, 2, 3):
        suffix = "" if i is None else f"_{i}"
        (tmp_path / f"2026-03-12_rechnung_telekom{suffix}.pdf").touch()
    assert next_available_name(
        tmp_path / "2026-03-12_rechnung_telekom.pdf"
    ) == tmp_path / "2026-03-12_rechnung_telekom_4.pdf"


def test_next_available_name_gives_up_eventually(tmp_path: Path):
    """If we somehow had >1000 collisions, we raise rather than loop forever."""
    base = tmp_path / "x.pdf"
    base.touch()
    for i in range(2, 1002):
        (tmp_path / f"x_{i}.pdf").touch()
    with pytest.raises(FileExistsError):
        next_available_name(base, max_attempts=1000)
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/unit/test_filename.py -v`
Expected: import error.

- [ ] **Step 3: Implement `src/aido/filing/filename.py`**

```python
"""Filename construction and collision handling."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from aido.filing.alias import slugify

_STEM_MAX = 80
_DOCTYPE_FALLBACK = "letter"
_PARTY_FALLBACK = "unknown"


def build_filename(doc_date: date, doctype: str, counterparty: str) -> str:
    """Return the canonical filename for a classified document.

    Format: ``YYYY-MM-DD_<doctype>_<counterparty>.pdf``. Empty doctype falls
    back to 'letter'; empty counterparty falls back to 'unknown'. The stem is
    truncated to {_STEM_MAX} characters (counterparty is the first to lose).
    """
    doctype_slug = slugify(doctype) or _DOCTYPE_FALLBACK
    party_slug = slugify(counterparty) or _PARTY_FALLBACK
    date_part = doc_date.isoformat()
    fixed = f"{date_part}_{doctype_slug}_"
    budget = _STEM_MAX - len(fixed)
    if budget < 1:
        # Pathological doctype length — keep at least one char of counterparty.
        budget = 1
    party_slug = party_slug[:budget].rstrip("-") or _PARTY_FALLBACK[:budget]
    return f"{fixed}{party_slug}.pdf"


def next_available_name(target: Path, *, max_attempts: int = 1000) -> Path:
    """Return `target` unchanged if it does not exist, else append `_2`, `_3`, ...

    Raises FileExistsError if more than `max_attempts` collisions are found.
    """
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    parent = target.parent
    for i in range(2, max_attempts + 1):
        candidate = parent / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
    raise FileExistsError(
        f"Could not find a free name for {target} after {max_attempts} attempts"
    )
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/unit/test_filename.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add src/aido/filing/filename.py tests/unit/test_filename.py
git commit -m "feat(filing): add build_filename and next_available_name"
```

---

## Task 4: PDF SHA-256 hashing + fixture synthesiser

**Files:**
- Create: `src/aido/pdf/hash.py`
- Create: `tests/fixtures.py`
- Test: `tests/unit/test_pdf_hash.py`

A simple hasher and a `synth_pdf()` helper used by later tests so we don't need to commit binary fixture PDFs to git.

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_pdf_hash.py
from pathlib import Path

from aido.pdf.hash import sha256_of_file
from tests.fixtures import synth_pdf


def test_sha256_is_stable(tmp_path: Path):
    a = tmp_path / "a.pdf"
    a.write_bytes(b"hello aido")
    assert sha256_of_file(a) == sha256_of_file(a)


def test_sha256_differs_for_different_content(tmp_path: Path):
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    a.write_bytes(b"hello aido")
    b.write_bytes(b"hello aido!")
    assert sha256_of_file(a) != sha256_of_file(b)


def test_synth_pdf_creates_readable_pdf(tmp_path: Path):
    p = synth_pdf(tmp_path / "invoice.pdf", text=["Rechnung", "Telekom GmbH", "100,00 EUR"])
    assert p.exists()
    assert p.read_bytes().startswith(b"%PDF-")
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/unit/test_pdf_hash.py -v`
Expected: import errors.

- [ ] **Step 3: Implement `src/aido/pdf/hash.py`**

```python
"""SHA-256 of a file on disk, streaming so big files don't blow memory."""
from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK = 64 * 1024


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()
```

- [ ] **Step 4: Implement `tests/fixtures.py`**

```python
"""Helpers for generating in-test PDF fixtures.

Uses fpdf2 (dev dep) so we don't ship binary fixtures in the repo.
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from fpdf import FPDF


def synth_pdf(target: Path, *, text: Sequence[str] = ("Test document",)) -> Path:
    """Create a minimal one-page PDF containing the given lines of text."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    for line in text:
        pdf.cell(0, 10, line, ln=1)
    target.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(target))
    return target


def synth_empty_pdf(target: Path) -> Path:
    """Create a PDF with no text content (a blank page)."""
    pdf = FPDF()
    pdf.add_page()
    target.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(target))
    return target
```

- [ ] **Step 5: Run tests, verify pass**

Run: `pytest tests/unit/test_pdf_hash.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add src/aido/pdf/hash.py tests/fixtures.py tests/unit/test_pdf_hash.py
git commit -m "feat(pdf): add sha256_of_file and fpdf2-based test PDF synth"
```

---

## Task 5: PDF text extraction

**Files:**
- Create: `src/aido/pdf/extract.py`
- Test: `tests/unit/test_pdf_extract.py`

`extract_text(path)` returns `(text, status)` where status is one of `ok`, `no_text`, `unreadable`. Truncates to ~6 KB (configurable) to keep prompt sizes bounded.

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_pdf_extract.py
from pathlib import Path

from aido.pdf.extract import ExtractStatus, extract_text
from tests.fixtures import synth_empty_pdf, synth_pdf


def test_extract_ok(tmp_path: Path):
    p = synth_pdf(tmp_path / "ok.pdf", text=["Rechnung", "Telekom GmbH"])
    text, status = extract_text(p)
    assert status == ExtractStatus.OK
    assert "Rechnung" in text
    assert "Telekom" in text


def test_extract_no_text_for_blank_pdf(tmp_path: Path):
    p = synth_empty_pdf(tmp_path / "blank.pdf")
    text, status = extract_text(p)
    assert status == ExtractStatus.NO_TEXT
    assert text == ""


def test_extract_unreadable_for_garbage_file(tmp_path: Path):
    p = tmp_path / "garbage.pdf"
    p.write_bytes(b"not a pdf at all")
    text, status = extract_text(p)
    assert status == ExtractStatus.UNREADABLE
    assert text == ""


def test_extract_truncates(tmp_path: Path):
    body = ["Line " + str(i) for i in range(2000)]
    p = synth_pdf(tmp_path / "long.pdf", text=body)
    text, status = extract_text(p, max_chars=1024)
    assert status == ExtractStatus.OK
    assert len(text) <= 1024
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/unit/test_pdf_extract.py -v`
Expected: import errors.

- [ ] **Step 3: Implement `src/aido/pdf/extract.py`**

```python
"""PDF text extraction using pypdf, with a tri-state outcome."""
from __future__ import annotations

from enum import Enum
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError, PyPdfError

DEFAULT_MAX_CHARS = 6 * 1024


class ExtractStatus(str, Enum):
    OK = "ok"
    NO_TEXT = "no_text"
    UNREADABLE = "unreadable"


def extract_text(path: Path, *, max_chars: int = DEFAULT_MAX_CHARS) -> tuple[str, ExtractStatus]:
    """Read embedded text from a PDF.

    Returns `(text, status)`. `text` is truncated to `max_chars`. Status:
    - OK: at least one non-whitespace character was extracted.
    - NO_TEXT: file parsed successfully but had no extractable text layer.
    - UNREADABLE: file could not be parsed (corrupt, encrypted, not a PDF).
    """
    try:
        reader = PdfReader(str(path))
    except (PdfReadError, PyPdfError, ValueError, OSError):
        return "", ExtractStatus.UNREADABLE

    if getattr(reader, "is_encrypted", False):
        return "", ExtractStatus.UNREADABLE

    parts: list[str] = []
    total = 0
    for page in reader.pages:
        try:
            page_text = page.extract_text() or ""
        except Exception:
            # Per-page extraction failure shouldn't abort the whole document.
            continue
        if not page_text:
            continue
        parts.append(page_text)
        total += len(page_text)
        if total >= max_chars:
            break

    text = "\n".join(parts)[:max_chars]
    if not text.strip():
        return "", ExtractStatus.NO_TEXT
    return text, ExtractStatus.OK
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/unit/test_pdf_extract.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/aido/pdf/extract.py tests/unit/test_pdf_extract.py
git commit -m "feat(pdf): add extract_text with tri-state outcome"
```

---

## Task 6: SQLite schema, connection, migrations

**Files:**
- Create: `src/aido/store/schema.sql`
- Create: `src/aido/store/connection.py`
- Create: `src/aido/store/migrations.py`
- Test: `tests/unit/test_store_connection.py`

`connect(path)` opens the DB, enables foreign keys + WAL + datetime type adapters, and returns a `sqlite3.Connection`. `init_db(conn)` is idempotent: it runs `schema.sql` only if the `persons` table is missing.

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_store_connection.py
from pathlib import Path

import pytest

from aido.store.connection import connect
from aido.store.migrations import init_db


def test_connect_creates_file(tmp_path: Path):
    db = tmp_path / "aido.sqlite"
    with connect(db) as conn:
        cur = conn.execute("SELECT 1")
        assert cur.fetchone() == (1,)
    assert db.exists()


def test_foreign_keys_are_enabled(tmp_path: Path):
    with connect(tmp_path / "x.sqlite") as conn:
        ((on,),) = list(conn.execute("PRAGMA foreign_keys"))
        assert on == 1


def test_journal_mode_is_wal(tmp_path: Path):
    with connect(tmp_path / "x.sqlite") as conn:
        ((mode,),) = list(conn.execute("PRAGMA journal_mode"))
        assert mode == "wal"


def test_init_db_creates_all_tables(tmp_path: Path):
    with connect(tmp_path / "x.sqlite") as conn:
        init_db(conn)
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    expected = {
        "persons",
        "person_aliases",
        "categories",
        "doctypes",
        "decisions",
        "manual_actions",
        "pending_jobs",
        "schema_version",
    }
    assert expected.issubset(tables)


def test_init_db_is_idempotent(tmp_path: Path):
    with connect(tmp_path / "x.sqlite") as conn:
        init_db(conn)
        init_db(conn)  # second call must not raise
        ((v,),) = list(conn.execute("SELECT MAX(version) FROM schema_version"))
        assert v == 1


def test_check_constraint_rejects_bad_status(tmp_path: Path):
    import sqlite3
    with connect(tmp_path / "x.sqlite") as conn:
        init_db(conn)
        # Need a person + category to satisfy FK on decisions; insert minimal seed.
        conn.execute(
            "INSERT INTO persons(slug, display_name, is_shared) VALUES (?, ?, 0)",
            ("timo", "Timo"),
        )
        conn.execute(
            "INSERT INTO categories(slug, display_name, is_review) VALUES (?, ?, 0)",
            ("rechnungen", "Rechnungen"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO decisions("
                "  created_at, source_hash, source_path, filed_path, person_id, "
                "  category_id, proposed_filename, overall_confidence, "
                "  person_confidence, category_confidence, classifier_model, "
                "  needs_review, status"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "2026-05-17T10:00:00", "h", "/s", "/d", 1, 1, "x.pdf",
                    0.9, 0.9, 0.9, "claude-opus-4-7", 0, "GARBAGE",
                ),
            )
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/unit/test_store_connection.py -v`
Expected: module/file missing.

- [ ] **Step 3: Implement `src/aido/store/schema.sql`**

```sql
-- aido v1 schema (single-file, STRICT-table model).
-- Run by aido.store.migrations.init_db().

CREATE TABLE schema_version (
  version    INTEGER PRIMARY KEY,
  applied_at TEXT    NOT NULL
) STRICT;

CREATE TABLE persons (
  id           INTEGER PRIMARY KEY,
  slug         TEXT    NOT NULL UNIQUE,
  display_name TEXT    NOT NULL,
  is_shared    INTEGER NOT NULL DEFAULT 0 CHECK (is_shared IN (0, 1)),
  is_active    INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
) STRICT;

CREATE TABLE person_aliases (
  id               INTEGER PRIMARY KEY,
  person_id        INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
  alias            TEXT    NOT NULL,
  alias_normalized TEXT    NOT NULL UNIQUE
) STRICT;
CREATE INDEX idx_aliases_normalized ON person_aliases(alias_normalized);
CREATE INDEX idx_aliases_person     ON person_aliases(person_id);

CREATE TABLE categories (
  id           INTEGER PRIMARY KEY,
  slug         TEXT    NOT NULL UNIQUE,
  display_name TEXT    NOT NULL,
  description  TEXT,
  is_review    INTEGER NOT NULL DEFAULT 0 CHECK (is_review IN (0, 1)),
  is_active    INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
) STRICT;

CREATE TABLE doctypes (
  id           INTEGER PRIMARY KEY,
  slug         TEXT    NOT NULL UNIQUE,
  display_name TEXT    NOT NULL,
  description  TEXT,
  is_active    INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
) STRICT;

CREATE TABLE decisions (
  id                    INTEGER PRIMARY KEY,
  created_at            TEXT    NOT NULL,              -- ISO8601 / via type adapters
  source_hash           TEXT    NOT NULL UNIQUE,
  source_path           TEXT    NOT NULL,
  filed_path            TEXT    NOT NULL,
  person_id             INTEGER NOT NULL REFERENCES persons(id),
  category_id           INTEGER NOT NULL REFERENCES categories(id),
  doctype_id            INTEGER          REFERENCES doctypes(id),
  document_date         TEXT,                          -- 'YYYY-MM-DD' or NULL
  counterparty          TEXT,
  proposed_filename     TEXT    NOT NULL,
  overall_confidence    REAL    NOT NULL CHECK (overall_confidence  BETWEEN 0 AND 1),
  person_confidence     REAL    NOT NULL CHECK (person_confidence   BETWEEN 0 AND 1),
  category_confidence   REAL    NOT NULL CHECK (category_confidence BETWEEN 0 AND 1),
  reasoning             TEXT,
  classifier_model      TEXT    NOT NULL,
  new_category_proposal TEXT,
  needs_review          INTEGER NOT NULL CHECK (needs_review IN (0, 1)),
  status                TEXT    NOT NULL CHECK (status IN
                            ('auto_filed', 'review', 'human_filed', 'failed'))
) STRICT;
CREATE INDEX idx_decisions_created ON decisions(created_at);
CREATE INDEX idx_decisions_status  ON decisions(status);
CREATE INDEX idx_decisions_person  ON decisions(person_id);

CREATE TABLE manual_actions (
  id                 INTEGER PRIMARY KEY,
  decision_id        INTEGER NOT NULL REFERENCES decisions(id),
  action             TEXT    NOT NULL CHECK (action IN
                         ('re_file', 'rename', 'delete', 'approve', 'promote_category')),
  before_path        TEXT    NOT NULL,
  after_path         TEXT,
  before_person_id   INTEGER          REFERENCES persons(id),
  after_person_id    INTEGER          REFERENCES persons(id),
  before_category_id INTEGER          REFERENCES categories(id),
  after_category_id  INTEGER          REFERENCES categories(id),
  created_at         TEXT    NOT NULL,
  note               TEXT
) STRICT;
CREATE INDEX idx_actions_decision ON manual_actions(decision_id);

CREATE TABLE pending_jobs (
  id              INTEGER PRIMARY KEY,
  source_path     TEXT    NOT NULL,
  source_hash     TEXT    NOT NULL UNIQUE,
  attempts        INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT    NOT NULL,
  last_error      TEXT,
  created_at      TEXT    NOT NULL
) STRICT;
CREATE INDEX idx_pending_next ON pending_jobs(next_attempt_at);
```

> **Note on STRICT + datetime:** STRICT tables require declared column types from the strict set (INTEGER, REAL, TEXT, BLOB, ANY). We store timestamps as ISO8601 TEXT and adapt to `datetime` on read in `connection.py`.

- [ ] **Step 4: Implement `src/aido/store/connection.py`**

```python
"""SQLite connection setup: pragmas, type adapters, helper functions."""
from __future__ import annotations

import contextlib
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Iterator


def _adapt_datetime(d: datetime) -> str:
    return d.isoformat(timespec="microseconds")


def _adapt_date(d: date) -> str:
    return d.isoformat()


def _convert_datetime(b: bytes) -> datetime:
    return datetime.fromisoformat(b.decode())


def _convert_date(b: bytes) -> date:
    return date.fromisoformat(b.decode())


_REGISTERED = False


def _register_adapters_once() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    sqlite3.register_adapter(datetime, _adapt_datetime)
    sqlite3.register_adapter(date, _adapt_date)
    sqlite3.register_converter("DATETIME", _convert_datetime)
    sqlite3.register_converter("DATE", _convert_date)
    _REGISTERED = True


@contextlib.contextmanager
def connect(path: Path | str) -> Iterator[sqlite3.Connection]:
    """Open a connection with pragmas + type detection configured.

    Yields a context-managed `sqlite3.Connection`. Commits on clean exit,
    rolls back on exception.
    """
    _register_adapters_once()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        str(path),
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        isolation_level=None,  # autocommit; we manage transactions ourselves
        check_same_thread=False,  # daemon worker + Flask handlers share one connection
    )
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA busy_timeout = 5000")  # wait up to 5s on writer contention
        conn.row_factory = sqlite3.Row
        yield conn
    finally:
        conn.close()
```

- [ ] **Step 5: Implement `src/aido/store/migrations.py`**

```python
"""DDL bootstrap. v1 has exactly one schema version."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def init_db(conn: sqlite3.Connection) -> None:
    """Apply DDL if the database is empty. Idempotent."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()
    if row is None:
        with conn:
            conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO schema_version(version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()),
            )
        return
    # Already initialised; ensure version row matches expectation.
    current = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    if current != SCHEMA_VERSION:
        raise RuntimeError(
            f"Unsupported schema version {current!r}; expected {SCHEMA_VERSION}"
        )
```

- [ ] **Step 6: Run tests, verify pass**

Run: `pytest tests/unit/test_store_connection.py -v`
Expected: 6 passed.

- [ ] **Step 7: Commit**

```bash
git add src/aido/store/schema.sql src/aido/store/connection.py src/aido/store/migrations.py tests/unit/test_store_connection.py
git commit -m "feat(store): add schema.sql, connection, and init_db"
```

---

## Task 7: persons + aliases repository

**Files:**
- Create: `src/aido/store/persons.py`
- Test: `tests/unit/test_store_persons.py`

Thin functional repository: each public function takes a `sqlite3.Connection` as first arg. No ORM. Returns plain dataclasses.

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_store_persons.py
import pytest

from aido.store.connection import connect
from aido.store.migrations import init_db
from aido.store.persons import (
    PersonRow,
    add_alias,
    create_person,
    find_person_by_alias,
    get_person_by_slug,
    list_aliases_for,
    list_persons,
)


@pytest.fixture
def conn(tmp_path):
    with connect(tmp_path / "x.sqlite") as c:
        init_db(c)
        yield c


def test_create_and_get_by_slug(conn):
    p = create_person(conn, slug="timo", display_name="Timo Jakob")
    assert isinstance(p, PersonRow)
    assert p.slug == "timo"
    assert p.display_name == "Timo Jakob"
    assert p.is_shared is False

    got = get_person_by_slug(conn, "timo")
    assert got == p


def test_create_shared(conn):
    p = create_person(conn, slug="shared", display_name="Shared", is_shared=True)
    assert p.is_shared is True


def test_list_persons_in_slug_order(conn):
    create_person(conn, slug="timo", display_name="Timo")
    create_person(conn, slug="anna", display_name="Anna")
    create_person(conn, slug="shared", display_name="Shared", is_shared=True)
    slugs = [p.slug for p in list_persons(conn)]
    assert slugs == ["anna", "shared", "timo"]


def test_add_alias_and_lookup_case_and_accent_insensitive(conn):
    p = create_person(conn, slug="penelope", display_name="Pénélope Müller")
    add_alias(conn, person_id=p.id, alias="Pénélope")
    add_alias(conn, person_id=p.id, alias="Penelope")
    add_alias(conn, person_id=p.id, alias="Müller")

    assert find_person_by_alias(conn, "penelope").id == p.id
    assert find_person_by_alias(conn, "PENÉLOPE").id == p.id
    assert find_person_by_alias(conn, " müller ").id == p.id
    assert find_person_by_alias(conn, "muller").id == p.id  # normalised match
    assert find_person_by_alias(conn, "unknown") is None


def test_alias_normalized_is_unique(conn):
    p1 = create_person(conn, slug="timo", display_name="Timo")
    p2 = create_person(conn, slug="other", display_name="Other")
    add_alias(conn, person_id=p1.id, alias="Jakob")
    with pytest.raises(Exception):  # IntegrityError under the hood
        add_alias(conn, person_id=p2.id, alias="jakob")


def test_list_aliases_for(conn):
    p = create_person(conn, slug="timo", display_name="Timo")
    add_alias(conn, person_id=p.id, alias="Jakob")
    add_alias(conn, person_id=p.id, alias="Jacob")
    aliases = list_aliases_for(conn, p.id)
    assert sorted(a.alias for a in aliases) == ["Jacob", "Jakob"]


def test_create_person_with_duplicate_slug_raises(conn):
    create_person(conn, slug="timo", display_name="Timo")
    with pytest.raises(Exception):
        create_person(conn, slug="timo", display_name="Other")
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/unit/test_store_persons.py -v`
Expected: import errors.

- [ ] **Step 3: Implement `src/aido/store/persons.py`**

```python
"""Persons + aliases repository."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from aido.filing.alias import alias_normalize


@dataclass(frozen=True, slots=True)
class PersonRow:
    id: int
    slug: str
    display_name: str
    is_shared: bool
    is_active: bool


@dataclass(frozen=True, slots=True)
class AliasRow:
    id: int
    person_id: int
    alias: str
    alias_normalized: str


def _row_to_person(row: sqlite3.Row) -> PersonRow:
    return PersonRow(
        id=row["id"],
        slug=row["slug"],
        display_name=row["display_name"],
        is_shared=bool(row["is_shared"]),
        is_active=bool(row["is_active"]),
    )


def _row_to_alias(row: sqlite3.Row) -> AliasRow:
    return AliasRow(
        id=row["id"],
        person_id=row["person_id"],
        alias=row["alias"],
        alias_normalized=row["alias_normalized"],
    )


def create_person(
    conn: sqlite3.Connection,
    *,
    slug: str,
    display_name: str,
    is_shared: bool = False,
    is_active: bool = True,
) -> PersonRow:
    cur = conn.execute(
        "INSERT INTO persons(slug, display_name, is_shared, is_active) VALUES (?, ?, ?, ?)",
        (slug, display_name, int(is_shared), int(is_active)),
    )
    return _person_by_id(conn, cur.lastrowid)


def _person_by_id(conn: sqlite3.Connection, person_id: int) -> PersonRow:
    row = conn.execute(
        "SELECT id, slug, display_name, is_shared, is_active FROM persons WHERE id = ?",
        (person_id,),
    ).fetchone()
    assert row is not None
    return _row_to_person(row)


def get_person_by_slug(conn: sqlite3.Connection, slug: str) -> PersonRow | None:
    row = conn.execute(
        "SELECT id, slug, display_name, is_shared, is_active FROM persons WHERE slug = ?",
        (slug,),
    ).fetchone()
    return _row_to_person(row) if row else None


def list_persons(conn: sqlite3.Connection, *, include_inactive: bool = False) -> list[PersonRow]:
    where = "" if include_inactive else "WHERE is_active = 1"
    rows = conn.execute(
        f"SELECT id, slug, display_name, is_shared, is_active FROM persons {where} ORDER BY slug"
    ).fetchall()
    return [_row_to_person(r) for r in rows]


def add_alias(conn: sqlite3.Connection, *, person_id: int, alias: str) -> AliasRow:
    normalized = alias_normalize(alias)
    cur = conn.execute(
        "INSERT INTO person_aliases(person_id, alias, alias_normalized) VALUES (?, ?, ?)",
        (person_id, alias, normalized),
    )
    row = conn.execute(
        "SELECT id, person_id, alias, alias_normalized FROM person_aliases WHERE id = ?",
        (cur.lastrowid,),
    ).fetchone()
    return _row_to_alias(row)


def list_aliases_for(conn: sqlite3.Connection, person_id: int) -> list[AliasRow]:
    rows = conn.execute(
        "SELECT id, person_id, alias, alias_normalized FROM person_aliases "
        "WHERE person_id = ? ORDER BY alias",
        (person_id,),
    ).fetchall()
    return [_row_to_alias(r) for r in rows]


def find_person_by_alias(conn: sqlite3.Connection, alias: str) -> PersonRow | None:
    normalized = alias_normalize(alias)
    row = conn.execute(
        "SELECT p.id, p.slug, p.display_name, p.is_shared, p.is_active "
        "FROM persons p JOIN person_aliases a ON a.person_id = p.id "
        "WHERE a.alias_normalized = ?",
        (normalized,),
    ).fetchone()
    return _row_to_person(row) if row else None
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/unit/test_store_persons.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/aido/store/persons.py tests/unit/test_store_persons.py
git commit -m "feat(store): add persons + aliases repository"
```

---

## Task 8: categories + doctypes repository

**Files:**
- Create: `src/aido/store/taxonomy.py`
- Test: `tests/unit/test_store_taxonomy.py`

Two symmetric tables; one module. Categories also support an `is_review` flag (true exactly once, for the `_review` row).

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_store_taxonomy.py
import pytest

from aido.store.connection import connect
from aido.store.migrations import init_db
from aido.store.taxonomy import (
    CategoryRow,
    DoctypeRow,
    create_category,
    create_doctype,
    get_category_by_slug,
    get_doctype_by_slug,
    get_review_category,
    list_categories,
    list_doctypes,
)


@pytest.fixture
def conn(tmp_path):
    with connect(tmp_path / "x.sqlite") as c:
        init_db(c)
        yield c


def test_create_and_get_category(conn):
    c = create_category(conn, slug="rechnungen", display_name="Rechnungen",
                        description="Eingehende Rechnungen")
    assert isinstance(c, CategoryRow)
    assert c.slug == "rechnungen"
    assert c.is_review is False

    assert get_category_by_slug(conn, "rechnungen") == c


def test_create_review_category(conn):
    c = create_category(conn, slug="_review", display_name="_review", is_review=True)
    assert c.is_review is True
    assert get_review_category(conn) == c


def test_list_categories_alphabetical_active_only(conn):
    create_category(conn, slug="steuer", display_name="Steuer")
    create_category(conn, slug="rechnungen", display_name="Rechnungen")
    create_category(conn, slug="archived", display_name="Archived", is_active=False)
    slugs = [c.slug for c in list_categories(conn)]
    assert slugs == ["rechnungen", "steuer"]
    slugs_all = [c.slug for c in list_categories(conn, include_inactive=True)]
    assert "archived" in slugs_all


def test_create_and_get_doctype(conn):
    d = create_doctype(conn, slug="rechnung", display_name="Rechnung",
                       description="Eine Rechnung von einem Anbieter")
    assert isinstance(d, DoctypeRow)
    assert get_doctype_by_slug(conn, "rechnung") == d


def test_list_doctypes(conn):
    create_doctype(conn, slug="rechnung", display_name="Rechnung")
    create_doctype(conn, slug="letter", display_name="Brief")
    slugs = [d.slug for d in list_doctypes(conn)]
    assert slugs == ["letter", "rechnung"]


def test_duplicate_slug_raises(conn):
    create_category(conn, slug="x", display_name="X")
    with pytest.raises(Exception):
        create_category(conn, slug="x", display_name="Y")
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/unit/test_store_taxonomy.py -v`
Expected: import errors.

- [ ] **Step 3: Implement `src/aido/store/taxonomy.py`**

```python
"""Categories + doctypes repository."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CategoryRow:
    id: int
    slug: str
    display_name: str
    description: str | None
    is_review: bool
    is_active: bool


@dataclass(frozen=True, slots=True)
class DoctypeRow:
    id: int
    slug: str
    display_name: str
    description: str | None
    is_active: bool


def _row_to_category(row: sqlite3.Row) -> CategoryRow:
    return CategoryRow(
        id=row["id"],
        slug=row["slug"],
        display_name=row["display_name"],
        description=row["description"],
        is_review=bool(row["is_review"]),
        is_active=bool(row["is_active"]),
    )


def _row_to_doctype(row: sqlite3.Row) -> DoctypeRow:
    return DoctypeRow(
        id=row["id"],
        slug=row["slug"],
        display_name=row["display_name"],
        description=row["description"],
        is_active=bool(row["is_active"]),
    )


_CAT_COLS = "id, slug, display_name, description, is_review, is_active"
_DT_COLS = "id, slug, display_name, description, is_active"


def create_category(
    conn: sqlite3.Connection,
    *,
    slug: str,
    display_name: str,
    description: str | None = None,
    is_review: bool = False,
    is_active: bool = True,
) -> CategoryRow:
    cur = conn.execute(
        "INSERT INTO categories(slug, display_name, description, is_review, is_active) "
        "VALUES (?, ?, ?, ?, ?)",
        (slug, display_name, description, int(is_review), int(is_active)),
    )
    row = conn.execute(
        f"SELECT {_CAT_COLS} FROM categories WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    return _row_to_category(row)


def get_category_by_slug(conn: sqlite3.Connection, slug: str) -> CategoryRow | None:
    row = conn.execute(
        f"SELECT {_CAT_COLS} FROM categories WHERE slug = ?", (slug,)
    ).fetchone()
    return _row_to_category(row) if row else None


def get_review_category(conn: sqlite3.Connection) -> CategoryRow | None:
    row = conn.execute(
        f"SELECT {_CAT_COLS} FROM categories WHERE is_review = 1 LIMIT 1"
    ).fetchone()
    return _row_to_category(row) if row else None


def list_categories(
    conn: sqlite3.Connection, *, include_inactive: bool = False
) -> list[CategoryRow]:
    where = "" if include_inactive else "WHERE is_active = 1"
    rows = conn.execute(
        f"SELECT {_CAT_COLS} FROM categories {where} ORDER BY slug"
    ).fetchall()
    return [_row_to_category(r) for r in rows]


def create_doctype(
    conn: sqlite3.Connection,
    *,
    slug: str,
    display_name: str,
    description: str | None = None,
    is_active: bool = True,
) -> DoctypeRow:
    cur = conn.execute(
        "INSERT INTO doctypes(slug, display_name, description, is_active) "
        "VALUES (?, ?, ?, ?)",
        (slug, display_name, description, int(is_active)),
    )
    row = conn.execute(
        f"SELECT {_DT_COLS} FROM doctypes WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    return _row_to_doctype(row)


def get_doctype_by_slug(conn: sqlite3.Connection, slug: str) -> DoctypeRow | None:
    row = conn.execute(
        f"SELECT {_DT_COLS} FROM doctypes WHERE slug = ?", (slug,)
    ).fetchone()
    return _row_to_doctype(row) if row else None


def list_doctypes(
    conn: sqlite3.Connection, *, include_inactive: bool = False
) -> list[DoctypeRow]:
    where = "" if include_inactive else "WHERE is_active = 1"
    rows = conn.execute(
        f"SELECT {_DT_COLS} FROM doctypes {where} ORDER BY slug"
    ).fetchall()
    return [_row_to_doctype(r) for r in rows]
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/unit/test_store_taxonomy.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/aido/store/taxonomy.py tests/unit/test_store_taxonomy.py
git commit -m "feat(store): add categories + doctypes repository"
```

---

## Task 9: decisions repository

**Files:**
- Create: `src/aido/store/decisions.py`
- Test: `tests/unit/test_store_decisions.py`

`insert_decision()`, `get_decision()`, `list_recent()`, `count_needs_review()`, `update_decision()` (used by mutations module). Also a `find_by_source_hash()` helper for dedupe.

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_store_decisions.py
from datetime import date, datetime, timezone

import pytest

from aido.store.connection import connect
from aido.store.decisions import (
    DecisionRow,
    DecisionUpdate,
    NewDecision,
    count_needs_review,
    find_by_source_hash,
    get_decision,
    insert_decision,
    list_recent,
    update_decision,
)
from aido.store.migrations import init_db
from aido.store.persons import create_person
from aido.store.taxonomy import create_category, create_doctype
from aido.types import DecisionStatus


@pytest.fixture
def ctx(tmp_path):
    with connect(tmp_path / "x.sqlite") as c:
        init_db(c)
        p = create_person(c, slug="timo", display_name="Timo Jakob")
        cat = create_category(c, slug="rechnungen", display_name="Rechnungen")
        dt = create_doctype(c, slug="rechnung", display_name="Rechnung")
        review = create_category(c, slug="_review", display_name="_review", is_review=True)
        yield c, p, cat, dt, review


def _sample(p_id: int, c_id: int, d_id: int | None, *, source_hash: str = "h1") -> NewDecision:
    return NewDecision(
        created_at=datetime(2026, 5, 17, 10, 0, tzinfo=timezone.utc),
        source_hash=source_hash,
        source_path="/scans/scan001.pdf",
        filed_path="/archive/timo/rechnungen/2026-03-12_rechnung_telekom.pdf",
        person_id=p_id,
        category_id=c_id,
        doctype_id=d_id,
        document_date=date(2026, 3, 12),
        counterparty="telekom",
        proposed_filename="2026-03-12_rechnung_telekom.pdf",
        overall_confidence=0.93,
        person_confidence=0.95,
        category_confidence=0.91,
        reasoning="recipient Timo Jakob; sender Telekom",
        classifier_model="claude-opus-4-7",
        new_category_proposal=None,
        needs_review=False,
        status=DecisionStatus.AUTO_FILED,
    )


def test_insert_and_get(ctx):
    conn, p, cat, dt, _ = ctx
    new_id = insert_decision(conn, _sample(p.id, cat.id, dt.id))
    got = get_decision(conn, new_id)
    assert isinstance(got, DecisionRow)
    assert got.id == new_id
    assert got.source_hash == "h1"
    assert got.status == DecisionStatus.AUTO_FILED
    assert got.document_date == date(2026, 3, 12)
    assert got.needs_review is False


def test_insert_duplicate_source_hash_raises(ctx):
    conn, p, cat, dt, _ = ctx
    insert_decision(conn, _sample(p.id, cat.id, dt.id))
    with pytest.raises(Exception):
        insert_decision(conn, _sample(p.id, cat.id, dt.id, source_hash="h1"))


def test_find_by_source_hash(ctx):
    conn, p, cat, dt, _ = ctx
    new_id = insert_decision(conn, _sample(p.id, cat.id, dt.id))
    assert find_by_source_hash(conn, "h1").id == new_id
    assert find_by_source_hash(conn, "nope") is None


def test_list_recent_orders_descending(ctx):
    conn, p, cat, dt, _ = ctx
    a = _sample(p.id, cat.id, dt.id, source_hash="a")
    b = _sample(p.id, cat.id, dt.id, source_hash="b")
    b = NewDecision(**{**b.__dict__, "created_at": datetime(2026, 5, 17, 11, 0, tzinfo=timezone.utc)})
    insert_decision(conn, a)
    insert_decision(conn, b)
    rows = list_recent(conn, limit=10)
    assert [r.source_hash for r in rows] == ["b", "a"]


def test_count_needs_review(ctx):
    conn, p, cat, dt, review = ctx
    insert_decision(conn, _sample(p.id, cat.id, dt.id, source_hash="a"))
    rv = _sample(p.id, review.id, None, source_hash="b")
    rv = NewDecision(**{**rv.__dict__, "needs_review": True, "status": DecisionStatus.REVIEW})
    insert_decision(conn, rv)
    assert count_needs_review(conn) == 1


def test_update_decision_changes_path_and_category(ctx):
    conn, p, cat, dt, _ = ctx
    other_cat = create_category(conn, slug="steuer", display_name="Steuer")
    new_id = insert_decision(conn, _sample(p.id, cat.id, dt.id))
    update_decision(
        conn,
        new_id,
        DecisionUpdate(
            filed_path="/archive/timo/steuer/x.pdf",
            category_id=other_cat.id,
            status=DecisionStatus.HUMAN_FILED,
            needs_review=False,
        ),
    )
    got = get_decision(conn, new_id)
    assert got.filed_path == "/archive/timo/steuer/x.pdf"
    assert got.category_id == other_cat.id
    assert got.status == DecisionStatus.HUMAN_FILED
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/unit/test_store_decisions.py -v`
Expected: import errors.

- [ ] **Step 3: Implement `src/aido/store/decisions.py`**

```python
"""Decisions repository."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime

from aido.types import DecisionStatus

_COLS = (
    "id, created_at AS 'created_at [DATETIME]', source_hash, source_path, filed_path, "
    "person_id, category_id, doctype_id, "
    "document_date AS 'document_date [DATE]', counterparty, proposed_filename, "
    "overall_confidence, person_confidence, category_confidence, "
    "reasoning, classifier_model, new_category_proposal, "
    "needs_review, status"
)


@dataclass(frozen=True, slots=True)
class NewDecision:
    created_at: datetime
    source_hash: str
    source_path: str
    filed_path: str
    person_id: int
    category_id: int
    doctype_id: int | None
    document_date: date | None
    counterparty: str | None
    proposed_filename: str
    overall_confidence: float
    person_confidence: float
    category_confidence: float
    reasoning: str | None
    classifier_model: str
    new_category_proposal: str | None
    needs_review: bool
    status: DecisionStatus


@dataclass(frozen=True, slots=True)
class DecisionRow:
    id: int
    created_at: datetime
    source_hash: str
    source_path: str
    filed_path: str
    person_id: int
    category_id: int
    doctype_id: int | None
    document_date: date | None
    counterparty: str | None
    proposed_filename: str
    overall_confidence: float
    person_confidence: float
    category_confidence: float
    reasoning: str | None
    classifier_model: str
    new_category_proposal: str | None
    needs_review: bool
    status: DecisionStatus


@dataclass(frozen=True, slots=True)
class DecisionUpdate:
    """Fields a manual action might change. None = leave alone."""
    filed_path: str | None = None
    person_id: int | None = None
    category_id: int | None = None
    doctype_id: int | None = None
    proposed_filename: str | None = None
    needs_review: bool | None = None
    status: DecisionStatus | None = None


def _row_to_decision(row: sqlite3.Row) -> DecisionRow:
    return DecisionRow(
        id=row["id"],
        created_at=row["created_at"],
        source_hash=row["source_hash"],
        source_path=row["source_path"],
        filed_path=row["filed_path"],
        person_id=row["person_id"],
        category_id=row["category_id"],
        doctype_id=row["doctype_id"],
        document_date=row["document_date"],
        counterparty=row["counterparty"],
        proposed_filename=row["proposed_filename"],
        overall_confidence=row["overall_confidence"],
        person_confidence=row["person_confidence"],
        category_confidence=row["category_confidence"],
        reasoning=row["reasoning"],
        classifier_model=row["classifier_model"],
        new_category_proposal=row["new_category_proposal"],
        needs_review=bool(row["needs_review"]),
        status=DecisionStatus(row["status"]),
    )


def insert_decision(conn: sqlite3.Connection, d: NewDecision) -> int:
    cur = conn.execute(
        "INSERT INTO decisions("
        "  created_at, source_hash, source_path, filed_path, person_id, category_id, "
        "  doctype_id, document_date, counterparty, proposed_filename, "
        "  overall_confidence, person_confidence, category_confidence, "
        "  reasoning, classifier_model, new_category_proposal, "
        "  needs_review, status"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            d.created_at, d.source_hash, d.source_path, d.filed_path,
            d.person_id, d.category_id, d.doctype_id,
            d.document_date, d.counterparty, d.proposed_filename,
            d.overall_confidence, d.person_confidence, d.category_confidence,
            d.reasoning, d.classifier_model, d.new_category_proposal,
            int(d.needs_review), d.status.value,
        ),
    )
    return cur.lastrowid


def get_decision(conn: sqlite3.Connection, decision_id: int) -> DecisionRow | None:
    row = conn.execute(
        f"SELECT {_COLS} FROM decisions WHERE id = ?", (decision_id,)
    ).fetchone()
    return _row_to_decision(row) if row else None


def find_by_source_hash(conn: sqlite3.Connection, source_hash: str) -> DecisionRow | None:
    row = conn.execute(
        f"SELECT {_COLS} FROM decisions WHERE source_hash = ?", (source_hash,)
    ).fetchone()
    return _row_to_decision(row) if row else None


def list_recent(
    conn: sqlite3.Connection,
    *,
    limit: int = 50,
    needs_review_only: bool = False,
) -> list[DecisionRow]:
    where = "WHERE needs_review = 1 " if needs_review_only else ""
    rows = conn.execute(
        f"SELECT {_COLS} FROM decisions {where}"
        "ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [_row_to_decision(r) for r in rows]


def count_needs_review(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM decisions WHERE needs_review = 1"
    ).fetchone()
    return row[0]


def update_decision(
    conn: sqlite3.Connection, decision_id: int, update: DecisionUpdate
) -> None:
    sets: list[str] = []
    params: list[object] = []
    if update.filed_path is not None:
        sets.append("filed_path = ?")
        params.append(update.filed_path)
    if update.person_id is not None:
        sets.append("person_id = ?")
        params.append(update.person_id)
    if update.category_id is not None:
        sets.append("category_id = ?")
        params.append(update.category_id)
    if update.doctype_id is not None:
        sets.append("doctype_id = ?")
        params.append(update.doctype_id)
    if update.proposed_filename is not None:
        sets.append("proposed_filename = ?")
        params.append(update.proposed_filename)
    if update.needs_review is not None:
        sets.append("needs_review = ?")
        params.append(int(update.needs_review))
    if update.status is not None:
        sets.append("status = ?")
        params.append(update.status.value)
    if not sets:
        return
    params.append(decision_id)
    conn.execute(f"UPDATE decisions SET {', '.join(sets)} WHERE id = ?", params)
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/unit/test_store_decisions.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/aido/store/decisions.py tests/unit/test_store_decisions.py
git commit -m "feat(store): add decisions repository"
```

---

## Task 10: manual_actions + pending_jobs repositories

**Files:**
- Create: `src/aido/store/manual_actions.py`
- Create: `src/aido/store/pending_jobs.py`
- Test: `tests/unit/test_store_pending.py`

Audit table is append-only. Pending jobs supports CRUD + a `claim_due()` helper for the retry loop.

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_store_pending.py
from datetime import datetime, timedelta, timezone

import pytest

from aido.store.connection import connect
from aido.store.manual_actions import (
    ManualActionRow,
    NewManualAction,
    insert_manual_action,
    list_actions_for_decision,
)
from aido.store.migrations import init_db
from aido.store.pending_jobs import (
    PendingJobRow,
    claim_due,
    delete_pending,
    enqueue_pending,
    record_attempt,
)
from aido.store.persons import create_person
from aido.store.taxonomy import create_category
from aido.types import ManualAction


@pytest.fixture
def conn(tmp_path):
    with connect(tmp_path / "x.sqlite") as c:
        init_db(c)
        yield c


def test_insert_and_list_manual_action(conn):
    p = create_person(conn, slug="timo", display_name="Timo")
    cat = create_category(conn, slug="x", display_name="X")
    # We need a decision id to FK to; minimal insert via raw SQL is fine.
    cur = conn.execute(
        "INSERT INTO decisions("
        "  created_at, source_hash, source_path, filed_path, person_id, category_id, "
        "  proposed_filename, overall_confidence, person_confidence, category_confidence, "
        "  classifier_model, needs_review, status"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("2026-05-17T10:00:00", "h", "/s", "/d", p.id, cat.id, "x.pdf",
         0.9, 0.9, 0.9, "claude-opus-4-7", 0, "auto_filed"),
    )
    decision_id = cur.lastrowid

    new_id = insert_manual_action(
        conn,
        NewManualAction(
            decision_id=decision_id,
            action=ManualAction.RE_FILE,
            before_path="/d",
            after_path="/d2",
            before_person_id=p.id,
            after_person_id=p.id,
            before_category_id=cat.id,
            after_category_id=cat.id,
            created_at=datetime(2026, 5, 17, 10, 5, tzinfo=timezone.utc),
            note=None,
        ),
    )
    rows = list_actions_for_decision(conn, decision_id)
    assert len(rows) == 1
    assert rows[0].id == new_id
    assert rows[0].action == ManualAction.RE_FILE


def test_enqueue_and_claim_due(conn):
    now = datetime(2026, 5, 17, 10, 0, tzinfo=timezone.utc)
    enqueue_pending(conn, source_path="/s/a.pdf", source_hash="h1",
                    next_attempt_at=now - timedelta(seconds=1), created_at=now)
    enqueue_pending(conn, source_path="/s/b.pdf", source_hash="h2",
                    next_attempt_at=now + timedelta(minutes=10), created_at=now)
    due = claim_due(conn, now=now, limit=10)
    hashes = [j.source_hash for j in due]
    assert hashes == ["h1"]


def test_record_attempt_increments_and_pushes_next_time(conn):
    now = datetime(2026, 5, 17, 10, 0, tzinfo=timezone.utc)
    enqueue_pending(conn, source_path="/s/a.pdf", source_hash="h1",
                    next_attempt_at=now, created_at=now)
    [job] = claim_due(conn, now=now, limit=10)
    record_attempt(conn, job.id, error="boom", next_attempt_at=now + timedelta(seconds=30))
    [updated] = claim_due(conn, now=now + timedelta(minutes=1), limit=10)
    assert updated.attempts == 1
    assert updated.last_error == "boom"


def test_delete_pending(conn):
    now = datetime(2026, 5, 17, 10, 0, tzinfo=timezone.utc)
    enqueue_pending(conn, source_path="/s/a.pdf", source_hash="h1",
                    next_attempt_at=now, created_at=now)
    [job] = claim_due(conn, now=now, limit=10)
    delete_pending(conn, job.id)
    assert claim_due(conn, now=now, limit=10) == []


def test_enqueue_duplicate_hash_raises(conn):
    now = datetime(2026, 5, 17, 10, 0, tzinfo=timezone.utc)
    enqueue_pending(conn, source_path="/s/a.pdf", source_hash="h1",
                    next_attempt_at=now, created_at=now)
    with pytest.raises(Exception):
        enqueue_pending(conn, source_path="/s/a.pdf", source_hash="h1",
                        next_attempt_at=now, created_at=now)
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/unit/test_store_pending.py -v`
Expected: import errors.

- [ ] **Step 3: Implement `src/aido/store/manual_actions.py`**

```python
"""Audit log of human-driven mutations."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from aido.types import ManualAction

_COLS = (
    "id, decision_id, action, before_path, after_path, "
    "before_person_id, after_person_id, before_category_id, after_category_id, "
    "created_at AS 'created_at [DATETIME]', note"
)


@dataclass(frozen=True, slots=True)
class NewManualAction:
    decision_id: int
    action: ManualAction
    before_path: str
    after_path: str | None
    before_person_id: int | None
    after_person_id: int | None
    before_category_id: int | None
    after_category_id: int | None
    created_at: datetime
    note: str | None


@dataclass(frozen=True, slots=True)
class ManualActionRow:
    id: int
    decision_id: int
    action: ManualAction
    before_path: str
    after_path: str | None
    before_person_id: int | None
    after_person_id: int | None
    before_category_id: int | None
    after_category_id: int | None
    created_at: datetime
    note: str | None


def _row_to_action(row: sqlite3.Row) -> ManualActionRow:
    return ManualActionRow(
        id=row["id"],
        decision_id=row["decision_id"],
        action=ManualAction(row["action"]),
        before_path=row["before_path"],
        after_path=row["after_path"],
        before_person_id=row["before_person_id"],
        after_person_id=row["after_person_id"],
        before_category_id=row["before_category_id"],
        after_category_id=row["after_category_id"],
        created_at=row["created_at"],
        note=row["note"],
    )


def insert_manual_action(conn: sqlite3.Connection, a: NewManualAction) -> int:
    cur = conn.execute(
        "INSERT INTO manual_actions("
        "  decision_id, action, before_path, after_path, "
        "  before_person_id, after_person_id, before_category_id, after_category_id, "
        "  created_at, note"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            a.decision_id, a.action.value, a.before_path, a.after_path,
            a.before_person_id, a.after_person_id,
            a.before_category_id, a.after_category_id,
            a.created_at, a.note,
        ),
    )
    return cur.lastrowid


def list_actions_for_decision(
    conn: sqlite3.Connection, decision_id: int
) -> list[ManualActionRow]:
    rows = conn.execute(
        f"SELECT {_COLS} FROM manual_actions WHERE decision_id = ? "
        "ORDER BY created_at ASC",
        (decision_id,),
    ).fetchall()
    return [_row_to_action(r) for r in rows]
```

- [ ] **Step 4: Implement `src/aido/store/pending_jobs.py`**

```python
"""Retry queue for classifier failures."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

_COLS = (
    "id, source_path, source_hash, attempts, "
    "next_attempt_at AS 'next_attempt_at [DATETIME]', "
    "last_error, "
    "created_at AS 'created_at [DATETIME]'"
)


@dataclass(frozen=True, slots=True)
class PendingJobRow:
    id: int
    source_path: str
    source_hash: str
    attempts: int
    next_attempt_at: datetime
    last_error: str | None
    created_at: datetime


def _row_to_job(row: sqlite3.Row) -> PendingJobRow:
    return PendingJobRow(
        id=row["id"],
        source_path=row["source_path"],
        source_hash=row["source_hash"],
        attempts=row["attempts"],
        next_attempt_at=row["next_attempt_at"],
        last_error=row["last_error"],
        created_at=row["created_at"],
    )


def enqueue_pending(
    conn: sqlite3.Connection,
    *,
    source_path: str,
    source_hash: str,
    next_attempt_at: datetime,
    created_at: datetime,
) -> int:
    cur = conn.execute(
        "INSERT INTO pending_jobs(source_path, source_hash, next_attempt_at, created_at) "
        "VALUES (?, ?, ?, ?)",
        (source_path, source_hash, next_attempt_at, created_at),
    )
    return cur.lastrowid


def claim_due(
    conn: sqlite3.Connection, *, now: datetime, limit: int = 10
) -> list[PendingJobRow]:
    rows = conn.execute(
        f"SELECT {_COLS} FROM pending_jobs WHERE next_attempt_at <= ? "
        "ORDER BY next_attempt_at ASC LIMIT ?",
        (now, limit),
    ).fetchall()
    return [_row_to_job(r) for r in rows]


def record_attempt(
    conn: sqlite3.Connection,
    job_id: int,
    *,
    error: str,
    next_attempt_at: datetime,
) -> None:
    conn.execute(
        "UPDATE pending_jobs SET attempts = attempts + 1, last_error = ?, "
        "next_attempt_at = ? WHERE id = ?",
        (error, next_attempt_at, job_id),
    )


def delete_pending(conn: sqlite3.Connection, job_id: int) -> None:
    conn.execute("DELETE FROM pending_jobs WHERE id = ?", (job_id,))
```

- [ ] **Step 5: Run tests, verify pass**

Run: `pytest tests/unit/test_store_pending.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add src/aido/store/manual_actions.py src/aido/store/pending_jobs.py tests/unit/test_store_pending.py
git commit -m "feat(store): add manual_actions + pending_jobs repositories"
```

---

## Task 11: Classifier Protocol + FakeClassifier

**Files:**
- Create: `src/aido/classifier/base.py`
- Create: `src/aido/classifier/fake.py`
- Test: `tests/unit/test_classifier_base.py`

`base.py` re-exports `ClassificationResult` (defined in `aido.types`) and declares the `Classifier` Protocol. `fake.py` provides a scriptable test double.

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_classifier_base.py
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
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/unit/test_classifier_base.py -v`
Expected: import errors.

- [ ] **Step 3: Implement `src/aido/classifier/base.py`**

```python
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
```

- [ ] **Step 4: Implement `src/aido/classifier/fake.py`**

```python
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
```

- [ ] **Step 5: Run tests, verify pass**

Run: `pytest tests/unit/test_classifier_base.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add src/aido/classifier/base.py src/aido/classifier/fake.py tests/unit/test_classifier_base.py
git commit -m "feat(classifier): add Classifier Protocol and FakeClassifier"
```

---

## Task 12: Routing — slug resolution + auto-file vs. review decision

**Files:**
- Create: `src/aido/classifier/routing.py`
- Test: `tests/unit/test_routing.py`

`route(conn, result, threshold)` resolves the classifier's slugs to DB IDs and decides whether a document is `auto_file` or `review`. Returns a `RouteDecision` dataclass containing the resolved IDs (or None) and a `RouteOutcome`.

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_routing.py
from datetime import date

import pytest

from aido.classifier.routing import RouteDecision, RouteReason, route
from aido.store.connection import connect
from aido.store.migrations import init_db
from aido.store.persons import create_person
from aido.store.taxonomy import create_category, create_doctype
from aido.types import ClassificationResult, RouteOutcome


@pytest.fixture
def conn(tmp_path):
    with connect(tmp_path / "x.sqlite") as c:
        init_db(c)
        create_person(c, slug="timo", display_name="Timo")
        create_person(c, slug="shared", display_name="Shared", is_shared=True)
        create_category(c, slug="rechnungen", display_name="Rechnungen")
        create_category(c, slug="_review", display_name="_review", is_review=True)
        create_doctype(c, slug="rechnung", display_name="Rechnung")
        create_doctype(c, slug="letter", display_name="Letter")
        yield c


def _r(**over):
    base = dict(
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
        reasoning="x",
    )
    base.update(over)
    return ClassificationResult(**base)


def test_high_confidence_auto_files(conn):
    decision = route(conn, _r(), threshold=0.75)
    assert decision.outcome == RouteOutcome.AUTO_FILE
    assert decision.person_id is not None
    assert decision.category_id is not None
    assert decision.doctype_id is not None
    assert decision.reason is None


def test_low_confidence_routes_to_review(conn):
    decision = route(conn, _r(overall_confidence=0.5), threshold=0.75)
    assert decision.outcome == RouteOutcome.REVIEW
    assert decision.reason == RouteReason.LOW_CONFIDENCE
    # Category is _review on review path.
    review_cat = decision.category_id
    assert review_cat is not None


def test_new_category_proposal_routes_to_review(conn):
    decision = route(
        conn,
        _r(new_category_proposal="garten", category_slug="rechnungen"),
        threshold=0.75,
    )
    assert decision.outcome == RouteOutcome.REVIEW
    assert decision.reason == RouteReason.NEW_CATEGORY_PROPOSAL


def test_unknown_person_slug_routes_to_review(conn):
    decision = route(conn, _r(person_slug="ghost"), threshold=0.75)
    assert decision.outcome == RouteOutcome.REVIEW
    assert decision.reason == RouteReason.UNKNOWN_PERSON


def test_unknown_category_slug_routes_to_review(conn):
    decision = route(conn, _r(category_slug="nope"), threshold=0.75)
    assert decision.outcome == RouteOutcome.REVIEW
    assert decision.reason == RouteReason.UNKNOWN_CATEGORY


def test_unknown_doctype_falls_back_to_letter(conn):
    # 'letter' exists from the fixture, so unknown doctype resolves to it.
    decision = route(conn, _r(doctype_slug="totally-unknown"), threshold=0.75)
    assert decision.outcome == RouteOutcome.AUTO_FILE
    # doctype_id resolved to the 'letter' fallback.
    assert decision.doctype_id is not None


def test_missing_review_category_raises(tmp_path):
    """If the DB has no _review row, routing is broken; surface loudly."""
    with connect(tmp_path / "y.sqlite") as c:
        init_db(c)
        create_person(c, slug="timo", display_name="Timo")
        create_category(c, slug="rechnungen", display_name="Rechnungen")
        with pytest.raises(RuntimeError, match="_review"):
            route(c, _r(overall_confidence=0.1), threshold=0.75)
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/unit/test_routing.py -v`
Expected: import errors.

- [ ] **Step 3: Implement `src/aido/classifier/routing.py`**

```python
"""Slug resolution + auto-file/review decision."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum

from aido.store.persons import get_person_by_slug
from aido.store.taxonomy import (
    get_category_by_slug,
    get_doctype_by_slug,
    get_review_category,
)
from aido.types import ClassificationResult, RouteOutcome

_DOCTYPE_FALLBACK_SLUG = "letter"


class RouteReason(str, Enum):
    LOW_CONFIDENCE = "low_confidence"
    NEW_CATEGORY_PROPOSAL = "new_category_proposal"
    UNKNOWN_PERSON = "unknown_person"
    UNKNOWN_CATEGORY = "unknown_category"


@dataclass(frozen=True, slots=True)
class RouteDecision:
    outcome: RouteOutcome
    person_id: int | None
    category_id: int | None  # _review category id when outcome=REVIEW and reason is known
    doctype_id: int | None
    reason: RouteReason | None  # None on AUTO_FILE


def route(
    conn: sqlite3.Connection,
    result: ClassificationResult,
    *,
    threshold: float,
) -> RouteDecision:
    """Resolve slugs to IDs and decide auto-file vs. review."""
    review_cat = get_review_category(conn)
    if review_cat is None:
        raise RuntimeError(
            "No _review category in the database; run 'aido init' before classifying."
        )

    person = get_person_by_slug(conn, result.person_slug)
    if person is None:
        return RouteDecision(
            outcome=RouteOutcome.REVIEW,
            person_id=None,
            category_id=review_cat.id,
            doctype_id=None,
            reason=RouteReason.UNKNOWN_PERSON,
        )

    category = get_category_by_slug(conn, result.category_slug)
    if category is None:
        return RouteDecision(
            outcome=RouteOutcome.REVIEW,
            person_id=person.id,
            category_id=review_cat.id,
            doctype_id=None,
            reason=RouteReason.UNKNOWN_CATEGORY,
        )

    doctype = get_doctype_by_slug(conn, result.doctype_slug)
    if doctype is None:
        # Fall back to the 'letter' generic doctype if available; else None.
        fallback = get_doctype_by_slug(conn, _DOCTYPE_FALLBACK_SLUG)
        doctype_id = fallback.id if fallback else None
    else:
        doctype_id = doctype.id

    if result.new_category_proposal:
        return RouteDecision(
            outcome=RouteOutcome.REVIEW,
            person_id=person.id,
            category_id=review_cat.id,
            doctype_id=doctype_id,
            reason=RouteReason.NEW_CATEGORY_PROPOSAL,
        )

    if result.overall_confidence < threshold:
        return RouteDecision(
            outcome=RouteOutcome.REVIEW,
            person_id=person.id,
            category_id=review_cat.id,
            doctype_id=doctype_id,
            reason=RouteReason.LOW_CONFIDENCE,
        )

    return RouteDecision(
        outcome=RouteOutcome.AUTO_FILE,
        person_id=person.id,
        category_id=category.id,
        doctype_id=doctype_id,
        reason=None,
    )
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/unit/test_routing.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/aido/classifier/routing.py tests/unit/test_routing.py
git commit -m "feat(classifier): add routing — slug resolution and auto-file/review decision"
```

---

## Task 13: Filing executor

**Files:**
- Create: `src/aido/filing/executor.py`
- Test: `tests/unit/test_filing_executor.py`

`file_document(src, archive_root, person_slug, category_slug, target_filename)` ensures the destination directory exists, picks a collision-free filename, and atomically moves the file. Returns the final `Path`. Removes the source on success.

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_filing_executor.py
from pathlib import Path

from aido.filing.executor import FilingTarget, file_document


def test_file_document_moves_into_person_category(tmp_path: Path):
    src = tmp_path / "inbox" / "scan001.pdf"
    src.parent.mkdir()
    src.write_bytes(b"x")
    archive = tmp_path / "archive"
    archive.mkdir()
    target = file_document(
        src,
        archive_root=archive,
        target=FilingTarget(
            person_slug="timo",
            category_slug="rechnungen",
            filename="2026-03-12_rechnung_telekom.pdf",
        ),
    )
    assert target == archive / "timo" / "rechnungen" / "2026-03-12_rechnung_telekom.pdf"
    assert target.exists()
    assert not src.exists()
    assert target.read_bytes() == b"x"


def test_file_document_to_review_uses_top_level(tmp_path: Path):
    src = tmp_path / "inbox" / "s.pdf"
    src.parent.mkdir()
    src.write_bytes(b"y")
    archive = tmp_path / "archive"
    archive.mkdir()
    target = file_document(
        src,
        archive_root=archive,
        target=FilingTarget(person_slug=None, category_slug="_review",
                            filename="2026-03-15_uncertain_low-confidence_unknown.pdf"),
    )
    assert target == archive / "_review" / "2026-03-15_uncertain_low-confidence_unknown.pdf"


def test_collision_appends_suffix(tmp_path: Path):
    archive = tmp_path / "archive"
    target_dir = archive / "timo" / "rechnungen"
    target_dir.mkdir(parents=True)
    (target_dir / "x.pdf").write_bytes(b"existing")

    src = tmp_path / "src.pdf"
    src.write_bytes(b"new")
    out = file_document(
        src,
        archive_root=archive,
        target=FilingTarget(person_slug="timo", category_slug="rechnungen", filename="x.pdf"),
    )
    assert out == target_dir / "x_2.pdf"
    assert out.read_bytes() == b"new"
    assert (target_dir / "x.pdf").read_bytes() == b"existing"


def test_creates_missing_directories(tmp_path: Path):
    src = tmp_path / "src.pdf"
    src.write_bytes(b"x")
    archive = tmp_path / "archive"
    out = file_document(
        src,
        archive_root=archive,
        target=FilingTarget(person_slug="anna", category_slug="medizin",
                            filename="2026-01-19_letter_helios.pdf"),
    )
    assert out.exists()
    assert out.parent == archive / "anna" / "medizin"
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/unit/test_filing_executor.py -v`
Expected: import errors.

- [ ] **Step 3: Implement `src/aido/filing/executor.py`**

```python
"""Atomic move of a PDF into the archive under <person>/<category>/."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from aido.filing.filename import next_available_name


@dataclass(frozen=True, slots=True)
class FilingTarget:
    """Where a document should land.

    `person_slug` is None for documents going into the top-level `_review/`
    bucket. `category_slug='_review'` + `person_slug=None` is the conventional
    pairing for the review bucket; other combinations are allowed but produce
    `<archive>/<person>/<category>/`.
    """

    person_slug: str | None
    category_slug: str
    filename: str


def _resolve_dir(archive_root: Path, target: FilingTarget) -> Path:
    if target.person_slug is None:
        return archive_root / target.category_slug
    return archive_root / target.person_slug / target.category_slug


def file_document(
    src: Path,
    *,
    archive_root: Path,
    target: FilingTarget,
) -> Path:
    """Move `src` to the resolved location inside `archive_root`.

    Creates parent directories as needed; resolves filename collisions by
    appending `_2`, `_3`, .... Uses `os.replace` so the move is atomic on the
    same filesystem.
    """
    dest_dir = _resolve_dir(archive_root, target)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = next_available_name(dest_dir / target.filename)
    os.replace(src, dest)
    return dest
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/unit/test_filing_executor.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/aido/filing/executor.py tests/unit/test_filing_executor.py
git commit -m "feat(filing): add filing executor with atomic move + collision handling"
```

---

## Task 14: Mutation API (re_file / rename / delete / approve / promote_category)

**Files:**
- Create: `src/aido/mutations.py`
- Test: `tests/unit/test_mutations.py`

These are the single-writer operations the worker thread and the web UI both call. Each function takes an explicit `threading.Lock` parameter so callers can share one across the daemon process. All operations write to the audit log (`manual_actions`) as part of the same DB transaction.

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_mutations.py
import threading
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from aido.mutations import (
    MutationContext,
    approve,
    delete_decision,
    promote_category,
    re_file,
    rename,
)
from aido.store.connection import connect
from aido.store.decisions import NewDecision, get_decision, insert_decision
from aido.store.manual_actions import list_actions_for_decision
from aido.store.migrations import init_db
from aido.store.persons import create_person
from aido.store.taxonomy import (
    create_category,
    create_doctype,
    get_category_by_slug,
)
from aido.types import DecisionStatus, ManualAction


@pytest.fixture
def ctx(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    with connect(tmp_path / "x.sqlite") as conn:
        init_db(conn)
        p_timo = create_person(conn, slug="timo", display_name="Timo")
        p_anna = create_person(conn, slug="anna", display_name="Anna")
        cat_re = create_category(conn, slug="rechnungen", display_name="Rechnungen")
        cat_st = create_category(conn, slug="steuer", display_name="Steuer")
        cat_rv = create_category(conn, slug="_review", display_name="_review", is_review=True)
        dt = create_doctype(conn, slug="rechnung", display_name="Rechnung")
        # Place a real file at the filed_path so re_file can move it.
        filed = archive / "timo" / "rechnungen" / "2026-03-12_rechnung_telekom.pdf"
        filed.parent.mkdir(parents=True)
        filed.write_bytes(b"pdf-bytes")
        new_id = insert_decision(
            conn,
            NewDecision(
                created_at=datetime(2026, 5, 17, 10, tzinfo=timezone.utc),
                source_hash="h1",
                source_path="/scans/scan001.pdf",
                filed_path=str(filed),
                person_id=p_timo.id,
                category_id=cat_re.id,
                doctype_id=dt.id,
                document_date=date(2026, 3, 12),
                counterparty="telekom",
                proposed_filename="2026-03-12_rechnung_telekom.pdf",
                overall_confidence=0.93,
                person_confidence=0.95,
                category_confidence=0.91,
                reasoning="x",
                classifier_model="claude-opus-4-7",
                new_category_proposal=None,
                needs_review=False,
                status=DecisionStatus.AUTO_FILED,
            ),
        )
        mctx = MutationContext(conn=conn, archive_root=archive, lock=threading.Lock(),
                               now=lambda: datetime(2026, 5, 17, 11, tzinfo=timezone.utc))
        yield {
            "ctx": mctx,
            "decision_id": new_id,
            "timo": p_timo,
            "anna": p_anna,
            "rechnungen": cat_re,
            "steuer": cat_st,
            "review": cat_rv,
        }


def test_re_file_moves_file_and_updates_decision(ctx):
    out = re_file(
        ctx["ctx"],
        ctx["decision_id"],
        person_id=ctx["anna"].id,
        category_id=ctx["steuer"].id,
        filename="2026-03-12_rechnung_telekom.pdf",
    )
    assert out.exists()
    assert out.parent.name == "steuer"
    assert out.parent.parent.name == "anna"
    d = get_decision(ctx["ctx"].conn, ctx["decision_id"])
    assert d.filed_path == str(out)
    assert d.person_id == ctx["anna"].id
    assert d.category_id == ctx["steuer"].id
    assert d.status == DecisionStatus.HUMAN_FILED
    [audit] = list_actions_for_decision(ctx["ctx"].conn, ctx["decision_id"])
    assert audit.action == ManualAction.RE_FILE


def test_rename_renames_in_place(ctx):
    out = rename(ctx["ctx"], ctx["decision_id"], filename="2026-03-12_rechnung_telekom-2.pdf")
    assert out.exists()
    assert out.name == "2026-03-12_rechnung_telekom-2.pdf"
    [audit] = list_actions_for_decision(ctx["ctx"].conn, ctx["decision_id"])
    assert audit.action == ManualAction.RENAME


def test_delete_removes_file_and_logs(ctx):
    delete_decision(ctx["ctx"], ctx["decision_id"], note="duplicate")
    d = get_decision(ctx["ctx"].conn, ctx["decision_id"])
    assert d.status == DecisionStatus.FAILED  # treated as 'no longer in archive'
    assert not Path(d.filed_path).exists()
    [audit] = list_actions_for_decision(ctx["ctx"].conn, ctx["decision_id"])
    assert audit.action == ManualAction.DELETE
    assert audit.note == "duplicate"


def test_approve_logs_and_marks_not_needs_review(ctx):
    # Flip the decision into needs_review first.
    ctx["ctx"].conn.execute(
        "UPDATE decisions SET needs_review = 1, status = ? WHERE id = ?",
        (DecisionStatus.REVIEW.value, ctx["decision_id"]),
    )
    approve(ctx["ctx"], ctx["decision_id"])
    d = get_decision(ctx["ctx"].conn, ctx["decision_id"])
    assert d.needs_review is False
    assert d.status == DecisionStatus.AUTO_FILED  # 'approve' means keep AI choice
    [audit] = list_actions_for_decision(ctx["ctx"].conn, ctx["decision_id"])
    assert audit.action == ManualAction.APPROVE


def test_promote_category_creates_category_and_refiles(ctx):
    new_cat = promote_category(
        ctx["ctx"],
        ctx["decision_id"],
        new_category_slug="garten",
        new_category_display_name="Garten",
        person_id=ctx["timo"].id,
        filename="2026-03-12_rechnung_telekom.pdf",
    )
    assert new_cat.slug == "garten"
    assert get_category_by_slug(ctx["ctx"].conn, "garten") is not None
    d = get_decision(ctx["ctx"].conn, ctx["decision_id"])
    assert d.category_id == new_cat.id
    assert Path(d.filed_path).parent.name == "garten"
    [audit] = list_actions_for_decision(ctx["ctx"].conn, ctx["decision_id"])
    assert audit.action == ManualAction.PROMOTE_CATEGORY
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/unit/test_mutations.py -v`
Expected: import errors.

- [ ] **Step 3: Implement `src/aido/mutations.py`**

```python
"""Single-writer mutation API used by both the worker thread and the web UI.

Each function acquires `MutationContext.lock` for the duration of the call so
that worker pipeline writes and HTTP-driven writes cannot race. All mutations
write to `manual_actions` as part of the same transaction.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from aido.filing.executor import FilingTarget, file_document
from aido.filing.filename import next_available_name
from aido.store.decisions import DecisionUpdate, get_decision, update_decision
from aido.store.manual_actions import NewManualAction, insert_manual_action
from aido.store.persons import get_person_by_slug
from aido.store.taxonomy import (
    CategoryRow,
    create_category,
    get_category_by_slug,
)
from aido.types import DecisionStatus, ManualAction


@dataclass(frozen=True, slots=True)
class MutationContext:
    conn: sqlite3.Connection
    archive_root: Path
    lock: threading.Lock
    now: Callable[[], datetime]


def _person_slug_or_none(ctx: MutationContext, person_id: int | None) -> str | None:
    if person_id is None:
        return None
    row = ctx.conn.execute(
        "SELECT slug, is_shared FROM persons WHERE id = ?", (person_id,)
    ).fetchone()
    if row is None:
        return None
    return row["slug"]


def _category_slug(ctx: MutationContext, category_id: int) -> str:
    row = ctx.conn.execute(
        "SELECT slug FROM categories WHERE id = ?", (category_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Unknown category id {category_id}")
    return row["slug"]


def re_file(
    ctx: MutationContext,
    decision_id: int,
    *,
    person_id: int,
    category_id: int,
    filename: str,
    note: str | None = None,
) -> Path:
    """Move the filed document to a new person/category, optionally renaming."""
    with ctx.lock:
        d = get_decision(ctx.conn, decision_id)
        if d is None:
            raise ValueError(f"Unknown decision id {decision_id}")
        src = Path(d.filed_path)
        if not src.exists():
            raise FileNotFoundError(f"Filed PDF missing: {src}")
        person_slug = _person_slug_or_none(ctx, person_id)
        cat_slug = _category_slug(ctx, category_id)
        dest = file_document(
            src,
            archive_root=ctx.archive_root,
            target=FilingTarget(
                person_slug=person_slug,
                category_slug=cat_slug,
                filename=filename,
            ),
        )
        with ctx.conn:
            update_decision(
                ctx.conn,
                decision_id,
                DecisionUpdate(
                    filed_path=str(dest),
                    person_id=person_id,
                    category_id=category_id,
                    proposed_filename=filename,
                    needs_review=False,
                    status=DecisionStatus.HUMAN_FILED,
                ),
            )
            insert_manual_action(
                ctx.conn,
                NewManualAction(
                    decision_id=decision_id,
                    action=ManualAction.RE_FILE,
                    before_path=str(src),
                    after_path=str(dest),
                    before_person_id=d.person_id,
                    after_person_id=person_id,
                    before_category_id=d.category_id,
                    after_category_id=category_id,
                    created_at=ctx.now(),
                    note=note,
                ),
            )
        return dest


def rename(
    ctx: MutationContext, decision_id: int, *, filename: str, note: str | None = None
) -> Path:
    """Rename the filed document in place."""
    with ctx.lock:
        d = get_decision(ctx.conn, decision_id)
        if d is None:
            raise ValueError(f"Unknown decision id {decision_id}")
        src = Path(d.filed_path)
        if not src.exists():
            raise FileNotFoundError(f"Filed PDF missing: {src}")
        dest = next_available_name(src.parent / filename)
        os.replace(src, dest)
        with ctx.conn:
            update_decision(
                ctx.conn,
                decision_id,
                DecisionUpdate(filed_path=str(dest), proposed_filename=filename),
            )
            insert_manual_action(
                ctx.conn,
                NewManualAction(
                    decision_id=decision_id,
                    action=ManualAction.RENAME,
                    before_path=str(src),
                    after_path=str(dest),
                    before_person_id=d.person_id,
                    after_person_id=d.person_id,
                    before_category_id=d.category_id,
                    after_category_id=d.category_id,
                    created_at=ctx.now(),
                    note=note,
                ),
            )
        return dest


def delete_decision(
    ctx: MutationContext, decision_id: int, *, note: str | None = None
) -> None:
    """Remove the filed PDF from disk and mark the decision FAILED."""
    with ctx.lock:
        d = get_decision(ctx.conn, decision_id)
        if d is None:
            raise ValueError(f"Unknown decision id {decision_id}")
        src = Path(d.filed_path)
        if src.exists():
            src.unlink()
        with ctx.conn:
            update_decision(
                ctx.conn,
                decision_id,
                DecisionUpdate(status=DecisionStatus.FAILED, needs_review=False),
            )
            insert_manual_action(
                ctx.conn,
                NewManualAction(
                    decision_id=decision_id,
                    action=ManualAction.DELETE,
                    before_path=str(src),
                    after_path=None,
                    before_person_id=d.person_id,
                    after_person_id=None,
                    before_category_id=d.category_id,
                    after_category_id=None,
                    created_at=ctx.now(),
                    note=note,
                ),
            )


def approve(
    ctx: MutationContext, decision_id: int, *, note: str | None = None
) -> None:
    """Accept the classifier's decision: clear `needs_review`, mark AUTO_FILED."""
    with ctx.lock:
        d = get_decision(ctx.conn, decision_id)
        if d is None:
            raise ValueError(f"Unknown decision id {decision_id}")
        with ctx.conn:
            update_decision(
                ctx.conn,
                decision_id,
                DecisionUpdate(
                    needs_review=False,
                    status=DecisionStatus.AUTO_FILED,
                ),
            )
            insert_manual_action(
                ctx.conn,
                NewManualAction(
                    decision_id=decision_id,
                    action=ManualAction.APPROVE,
                    before_path=d.filed_path,
                    after_path=d.filed_path,
                    before_person_id=d.person_id,
                    after_person_id=d.person_id,
                    before_category_id=d.category_id,
                    after_category_id=d.category_id,
                    created_at=ctx.now(),
                    note=note,
                ),
            )


def promote_category(
    ctx: MutationContext,
    decision_id: int,
    *,
    new_category_slug: str,
    new_category_display_name: str,
    person_id: int,
    filename: str,
    note: str | None = None,
) -> CategoryRow:
    """Create a new category from a proposal, then re-file the document into it."""
    with ctx.lock:
        d = get_decision(ctx.conn, decision_id)
        if d is None:
            raise ValueError(f"Unknown decision id {decision_id}")
        existing = get_category_by_slug(ctx.conn, new_category_slug)
        if existing is not None:
            new_cat = existing
        else:
            with ctx.conn:
                new_cat = create_category(
                    ctx.conn,
                    slug=new_category_slug,
                    display_name=new_category_display_name,
                )

        src = Path(d.filed_path)
        if not src.exists():
            raise FileNotFoundError(f"Filed PDF missing: {src}")
        person_slug = _person_slug_or_none(ctx, person_id)
        dest = file_document(
            src,
            archive_root=ctx.archive_root,
            target=FilingTarget(
                person_slug=person_slug,
                category_slug=new_cat.slug,
                filename=filename,
            ),
        )
        with ctx.conn:
            update_decision(
                ctx.conn,
                decision_id,
                DecisionUpdate(
                    filed_path=str(dest),
                    person_id=person_id,
                    category_id=new_cat.id,
                    proposed_filename=filename,
                    needs_review=False,
                    status=DecisionStatus.HUMAN_FILED,
                ),
            )
            insert_manual_action(
                ctx.conn,
                NewManualAction(
                    decision_id=decision_id,
                    action=ManualAction.PROMOTE_CATEGORY,
                    before_path=str(src),
                    after_path=str(dest),
                    before_person_id=d.person_id,
                    after_person_id=person_id,
                    before_category_id=d.category_id,
                    after_category_id=new_cat.id,
                    created_at=ctx.now(),
                    note=note,
                ),
            )
        return new_cat
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/unit/test_mutations.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/aido/mutations.py tests/unit/test_mutations.py
git commit -m "feat(mutations): add re_file/rename/delete/approve/promote_category API"
```

---

## Task 15: Config loader

**Files:**
- Create: `src/aido/config.py`
- Create: `config.example.yaml`
- Test: `tests/unit/test_config.py`

`load_config(path)` parses the YAML, validates the shape, returns a frozen `Config` dataclass. Unknown classifier backends raise. `config.example.yaml` ships as a template.

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_config.py
from pathlib import Path

import pytest

from aido.config import (
    ClassifierBackend,
    ClassifierConfig,
    Config,
    WebConfig,
    load_config,
)


def _write(p: Path, body: str) -> Path:
    p.write_text(body, encoding="utf-8")
    return p


def test_loads_valid_config(tmp_path: Path):
    cfg_path = _write(tmp_path / "config.yaml", """
archive_root: /archive
scan_inbox: /scans
db_path: /data/aido.sqlite
log_path: /var/log/aido/aido.log

classifier:
  backend: agent_sdk
  model: claude-opus-4-7
  review_confidence_threshold: 0.75

web:
  bind: 0.0.0.0
  port: 8765
""".strip())

    cfg = load_config(cfg_path)
    assert isinstance(cfg, Config)
    assert cfg.archive_root == Path("/archive")
    assert cfg.scan_inbox == Path("/scans")
    assert cfg.classifier.backend == ClassifierBackend.AGENT_SDK
    assert cfg.classifier.model == "claude-opus-4-7"
    assert cfg.classifier.review_confidence_threshold == 0.75
    assert cfg.web.bind == "0.0.0.0"
    assert cfg.web.port == 8765


def test_unknown_backend_raises(tmp_path: Path):
    cfg_path = _write(tmp_path / "config.yaml", """
archive_root: /a
scan_inbox: /s
db_path: /d.sqlite
log_path: /l.log
classifier:
  backend: rocketship
  model: x
  review_confidence_threshold: 0.5
web:
  bind: 0.0.0.0
  port: 8765
""".strip())
    with pytest.raises(ValueError, match="rocketship"):
        load_config(cfg_path)


def test_missing_required_key_raises(tmp_path: Path):
    cfg_path = _write(tmp_path / "config.yaml", "archive_root: /a\n")
    with pytest.raises(ValueError, match="scan_inbox"):
        load_config(cfg_path)


def test_threshold_out_of_range_raises(tmp_path: Path):
    cfg_path = _write(tmp_path / "config.yaml", """
archive_root: /a
scan_inbox: /s
db_path: /d.sqlite
log_path: /l.log
classifier:
  backend: agent_sdk
  model: x
  review_confidence_threshold: 1.5
web:
  bind: 0.0.0.0
  port: 8765
""".strip())
    with pytest.raises(ValueError, match="threshold"):
        load_config(cfg_path)
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/unit/test_config.py -v`
Expected: import errors.

- [ ] **Step 3: Implement `src/aido/config.py`**

```python
"""YAML config loader for aido."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ruamel.yaml import YAML


class ClassifierBackend(str, Enum):
    AGENT_SDK = "agent_sdk"
    ANTHROPIC_API = "anthropic_api"
    LOCAL_LLM = "local_llm"
    FAKE = "fake"  # for tests


@dataclass(frozen=True, slots=True)
class ClassifierConfig:
    backend: ClassifierBackend
    model: str
    review_confidence_threshold: float


@dataclass(frozen=True, slots=True)
class WebConfig:
    bind: str
    port: int


@dataclass(frozen=True, slots=True)
class Config:
    archive_root: Path
    scan_inbox: Path
    db_path: Path
    log_path: Path
    classifier: ClassifierConfig
    web: WebConfig


def _require(d: dict, key: str) -> object:
    if key not in d:
        raise ValueError(f"Missing required config key: {key}")
    return d[key]


def load_config(path: Path) -> Config:
    yaml = YAML(typ="safe")
    raw = yaml.load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} is not a YAML mapping")

    cls = _require(raw, "classifier")
    if not isinstance(cls, dict):
        raise ValueError("classifier must be a mapping")
    backend_raw = _require(cls, "backend")
    try:
        backend = ClassifierBackend(backend_raw)
    except ValueError as e:
        raise ValueError(f"Unknown classifier backend: {backend_raw!r}") from e
    threshold = float(_require(cls, "review_confidence_threshold"))
    if not (0.0 <= threshold <= 1.0):
        raise ValueError(f"classifier.review_confidence_threshold must be in [0, 1] (got {threshold})")

    web = _require(raw, "web")
    if not isinstance(web, dict):
        raise ValueError("web must be a mapping")

    return Config(
        archive_root=Path(str(_require(raw, "archive_root"))),
        scan_inbox=Path(str(_require(raw, "scan_inbox"))),
        db_path=Path(str(_require(raw, "db_path"))),
        log_path=Path(str(_require(raw, "log_path"))),
        classifier=ClassifierConfig(
            backend=backend,
            model=str(_require(cls, "model")),
            review_confidence_threshold=threshold,
        ),
        web=WebConfig(
            bind=str(_require(web, "bind")),
            port=int(_require(web, "port")),
        ),
    )
```

- [ ] **Step 4: Write `config.example.yaml`**

```yaml
# aido configuration. Mounted read-only into the container at /app/config.yaml.

archive_root: /archive
scan_inbox: /scans
db_path: /data/aido.sqlite
log_path: /var/log/aido/aido.log

classifier:
  backend: agent_sdk                  # agent_sdk | anthropic_api | local_llm | fake
  model: claude-opus-4-7
  review_confidence_threshold: 0.75

web:
  bind: 0.0.0.0                       # bound inside the container; Docker maps to host
  port: 8765
```

- [ ] **Step 5: Run tests, verify pass**

Run: `pytest tests/unit/test_config.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add src/aido/config.py config.example.yaml tests/unit/test_config.py
git commit -m "feat(config): add YAML config loader + example"
```

---

## Task 16: Structured JSON logging + rotation

**Files:**
- Create: `src/aido/logging_setup.py`
- Test: `tests/unit/test_logging.py`

`configure_logging(log_path)` installs a `RotatingFileHandler` writing one JSON object per line. Extra fields passed via `logger.info("...", extra={"source_hash": ...})` end up in the JSON.

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_logging.py
import json
import logging
from pathlib import Path

import pytest

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
            name="aido.test", level=logging.ERROR, pathname=__file__, lineno=1,
            msg="oops", args=(), exc_info=True,
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
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/unit/test_logging.py -v`
Expected: import errors.

- [ ] **Step 3: Implement `src/aido/logging_setup.py`**

```python
"""Structured JSON logger + RotatingFileHandler."""
from __future__ import annotations

import json
import logging
import logging.handlers
from datetime import datetime, timezone
from pathlib import Path

_BUILTIN = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "asctime", "message",
}


class JsonFormatter(logging.Formatter):
    """Formats a `LogRecord` as a single JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _BUILTIN or key.startswith("_"):
                continue
            out[key] = value
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)


_CONFIGURED = False


def configure_logging(log_path: Path) -> logging.Logger:
    """Install one rotating file handler on the 'aido' logger. Idempotent."""
    global _CONFIGURED
    logger = logging.getLogger("aido")
    if _CONFIGURED:
        return logger
    logger.setLevel(logging.INFO)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.TimedRotatingFileHandler(
        log_path, when="W0", backupCount=8, encoding="utf-8"
    )
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    _CONFIGURED = True
    return logger
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/unit/test_logging.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/aido/logging_setup.py tests/unit/test_logging.py
git commit -m "feat(logging): add JSON formatter + rotating file handler"
```

---

## Task 17: AgentSDKClassifier

**Files:**
- Create: `src/aido/classifier/agent_sdk.py`
- Test: `tests/unit/test_agent_sdk.py`

Builds a system prompt from the current DB taxonomy, calls `claude_agent_sdk.query(...)`, parses the JSON response, returns a `ClassificationResult`. Network is mocked in tests via `pytest-mock`. The Agent SDK call returns an async iterator of message blocks; we consume them and concatenate text.

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_agent_sdk.py
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
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/unit/test_agent_sdk.py -v`
Expected: import errors.

- [ ] **Step 3: Implement `src/aido/classifier/agent_sdk.py`**

```python
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
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/unit/test_agent_sdk.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/aido/classifier/agent_sdk.py tests/unit/test_agent_sdk.py
git commit -m "feat(classifier): add AgentSDKClassifier using Max Plan OAuth"
```

---

## Task 18: AnthropicAPIClassifier (fallback)

**Files:**
- Create: `src/aido/classifier/anthropic_api.py`
- Test: `tests/unit/test_anthropic_api.py`

Mirror of `agent_sdk.py` using the direct `anthropic` SDK. Same system-prompt builder is re-used. Use Anthropic's prompt caching by marking the system block with `cache_control: ephemeral`.

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_anthropic_api.py
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
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/unit/test_anthropic_api.py -v`
Expected: import errors.

- [ ] **Step 3: Implement `src/aido/classifier/anthropic_api.py`**

```python
"""AnthropicAPIClassifier — opportunistic fallback using direct API key."""
from __future__ import annotations

import sqlite3

from anthropic import Anthropic

from aido.classifier.agent_sdk import _parse_response, _build_user_prompt, build_system_prompt
from aido.types import ClassificationResult


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
        raw = "".join(getattr(b, "text", "") for b in response.content)
        return _parse_response(raw)
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/unit/test_anthropic_api.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add src/aido/classifier/anthropic_api.py tests/unit/test_anthropic_api.py
git commit -m "feat(classifier): add AnthropicAPIClassifier fallback"
```

---

## Task 19: Classifier factory

**Files:**
- Create: `src/aido/classifier/factory.py`
- Test: `tests/unit/test_factory.py`

`build_classifier(conn, classifier_config)` returns the appropriate concrete classifier based on `backend`. `local_llm` raises `NotImplementedError` (post-MVP). `fake` returns a `FakeClassifier([])` — only used by tests that re-populate it themselves.

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_factory.py
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
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/unit/test_factory.py -v`
Expected: module missing.

- [ ] **Step 3: Implement `src/aido/classifier/factory.py`**

```python
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
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/unit/test_factory.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/aido/classifier/factory.py tests/unit/test_factory.py
git commit -m "feat(classifier): add build_classifier factory"
```

---

## Task 20: Inbox queue

**Files:**
- Create: `src/aido/worker/queue.py`
- Test: `tests/unit/test_queue.py`

A thin wrapper around `queue.Queue[Path]` so the watcher pushes new PDFs and the worker consumes. Adds a `drain_existing(inbox)` helper called once at startup to enqueue any PDFs already in the inbox (no inotify event for them).

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_queue.py
from pathlib import Path

import pytest

from aido.worker.queue import InboxQueue


def test_put_get_roundtrip():
    q = InboxQueue()
    q.put(Path("/scans/a.pdf"))
    assert q.get(timeout=0.1) == Path("/scans/a.pdf")


def test_get_returns_none_on_timeout():
    q = InboxQueue()
    assert q.get(timeout=0.05) is None


def test_drain_existing_enqueues_pdfs(tmp_path: Path):
    (tmp_path / "a.pdf").touch()
    (tmp_path / "b.PDF").touch()  # case-insensitive
    (tmp_path / "ignore.txt").touch()
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.pdf").touch()  # nested ignored

    q = InboxQueue()
    q.drain_existing(tmp_path)
    seen = set()
    while item := q.get(timeout=0.05):
        seen.add(item.name)
    assert seen == {"a.pdf", "b.PDF"}


def test_drain_existing_skips_hidden_files(tmp_path: Path):
    (tmp_path / ".hidden.pdf").touch()
    (tmp_path / "real.pdf").touch()
    q = InboxQueue()
    q.drain_existing(tmp_path)
    seen = []
    while item := q.get(timeout=0.05):
        seen.append(item.name)
    assert seen == ["real.pdf"]
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/unit/test_queue.py -v`
Expected: import errors.

- [ ] **Step 3: Implement `src/aido/worker/queue.py`**

```python
"""Single-producer queue between watcher and worker."""
from __future__ import annotations

import queue
from pathlib import Path


class InboxQueue:
    """Thread-safe FIFO of paths for the worker to process."""

    def __init__(self) -> None:
        self._q: queue.Queue[Path] = queue.Queue()

    def put(self, path: Path) -> None:
        self._q.put(path)

    def get(self, timeout: float = 1.0) -> Path | None:
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None

    def drain_existing(self, inbox: Path) -> None:
        """Enqueue every top-level PDF currently in `inbox`. Skips dotfiles."""
        for entry in sorted(inbox.iterdir()):
            if entry.is_file() and not entry.name.startswith(".") \
                    and entry.suffix.lower() == ".pdf":
                self.put(entry)
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/unit/test_queue.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/aido/worker/queue.py tests/unit/test_queue.py
git commit -m "feat(worker): add InboxQueue with drain_existing helper"
```

---

## Task 21: Worker pipeline (process_one_document)

**Files:**
- Create: `src/aido/worker/pipeline.py`
- Test: `tests/unit/test_pipeline.py`

The orchestration layer: stabilize → dedupe → extract → classify → route → file → record decision. All exceptions are caught; the function never raises out. Returns a `PipelineOutcome` dataclass describing what happened (auto_filed / review / duplicate_skip / failed) for logging and tests.

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_pipeline.py
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from aido.classifier.fake import FakeClassifier
from aido.mutations import MutationContext
from aido.store.connection import connect
from aido.store.decisions import find_by_source_hash, get_decision
from aido.store.migrations import init_db
from aido.store.persons import create_person
from aido.store.taxonomy import create_category, create_doctype
from aido.types import ClassificationResult, DecisionStatus
from aido.worker.pipeline import PipelineOutcome, Pipeline
from tests.fixtures import synth_empty_pdf, synth_pdf


def _result(**over) -> ClassificationResult:
    base = dict(
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
        reasoning="r",
    )
    base.update(over)
    return ClassificationResult(**base)


@pytest.fixture
def setup(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    with connect(tmp_path / "x.sqlite") as conn:
        init_db(conn)
        create_person(conn, slug="timo", display_name="Timo Jakob")
        create_category(conn, slug="rechnungen", display_name="Rechnungen")
        create_category(conn, slug="_review", display_name="_review", is_review=True)
        create_doctype(conn, slug="rechnung", display_name="Rechnung")
        create_doctype(conn, slug="letter", display_name="Letter")
        mctx = MutationContext(
            conn=conn,
            archive_root=archive,
            lock=threading.Lock(),
            now=lambda: datetime(2026, 5, 17, 10, tzinfo=timezone.utc),
        )
        yield {"conn": conn, "archive": archive, "mctx": mctx, "tmp": tmp_path}


def test_high_confidence_auto_files(setup):
    pdf = synth_pdf(setup["tmp"] / "scan001.pdf", text=["Rechnung", "Telekom"])
    fake = FakeClassifier(results=[_result()])
    pipe = Pipeline(
        conn=setup["conn"],
        classifier=fake,
        threshold=0.75,
        mutations=setup["mctx"],
        classifier_model="claude-opus-4-7",
        stabilize_seconds=0.0,
    )
    outcome = pipe.process(pdf)
    assert outcome == PipelineOutcome.AUTO_FILED
    decision = find_by_source_hash(setup["conn"], _hash_of(pdf))
    assert decision is not None
    assert decision.status == DecisionStatus.AUTO_FILED
    assert Path(decision.filed_path).exists()
    assert not pdf.exists()


def test_low_confidence_routes_to_review(setup):
    pdf = synth_pdf(setup["tmp"] / "scan001.pdf", text=["Rechnung"])
    fake = FakeClassifier(results=[_result(overall_confidence=0.4)])
    pipe = Pipeline(
        conn=setup["conn"],
        classifier=fake,
        threshold=0.75,
        mutations=setup["mctx"],
        classifier_model="claude-opus-4-7",
        stabilize_seconds=0.0,
    )
    outcome = pipe.process(pdf)
    assert outcome == PipelineOutcome.REVIEW
    decision = find_by_source_hash(setup["conn"], _hash_of(pdf))
    assert decision.status == DecisionStatus.REVIEW
    assert decision.needs_review is True
    assert (setup["archive"] / "_review").exists()


def test_pdf_without_text_routes_to_review(setup):
    pdf = synth_empty_pdf(setup["tmp"] / "blank.pdf")
    fake = FakeClassifier(results=[])  # should never be called
    pipe = Pipeline(
        conn=setup["conn"],
        classifier=fake,
        threshold=0.75,
        mutations=setup["mctx"],
        classifier_model="claude-opus-4-7",
        stabilize_seconds=0.0,
    )
    outcome = pipe.process(pdf)
    assert outcome == PipelineOutcome.REVIEW
    assert fake.calls == []


def test_duplicate_is_skipped(setup):
    pdf = synth_pdf(setup["tmp"] / "scan001.pdf", text=["Rechnung", "Telekom"])
    # First run files it.
    pipe = Pipeline(
        conn=setup["conn"],
        classifier=FakeClassifier(results=[_result()]),
        threshold=0.75,
        mutations=setup["mctx"],
        classifier_model="claude-opus-4-7",
        stabilize_seconds=0.0,
    )
    assert pipe.process(pdf) == PipelineOutcome.AUTO_FILED

    # Second time same content arrives in inbox.
    dup = synth_pdf(setup["tmp"] / "scan002.pdf", text=["Rechnung", "Telekom"])
    outcome = pipe.process(dup)
    assert outcome == PipelineOutcome.DUPLICATE_SKIP
    assert not dup.exists()  # removed from inbox


def test_classifier_exception_routes_to_review(setup):
    pdf = synth_pdf(setup["tmp"] / "scan001.pdf", text=["Hello"])
    fake = FakeClassifier(results=[RuntimeError("api timeout")])
    pipe = Pipeline(
        conn=setup["conn"],
        classifier=fake,
        threshold=0.75,
        mutations=setup["mctx"],
        classifier_model="claude-opus-4-7",
        stabilize_seconds=0.0,
    )
    outcome = pipe.process(pdf)
    assert outcome == PipelineOutcome.REVIEW
    decision = find_by_source_hash(setup["conn"], _hash_of(pdf))
    assert decision is not None
    assert decision.needs_review is True
    assert "api timeout" in (decision.reasoning or "")


def _hash_of(path: Path) -> str:
    from aido.pdf.hash import sha256_of_file
    return sha256_of_file(path)
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/unit/test_pipeline.py -v`
Expected: import errors.

- [ ] **Step 3: Implement `src/aido/worker/pipeline.py`**

```python
"""End-to-end processing of a single PDF.

Catches every exception. Never raises out of `process()`. Returns a
`PipelineOutcome` describing what happened, so callers can log it.
"""
from __future__ import annotations

import logging
import sqlite3
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from aido.classifier.base import Classifier
from aido.classifier.routing import RouteDecision, RouteReason, route
from aido.filing.executor import FilingTarget, file_document
from aido.mutations import MutationContext
from aido.pdf.extract import ExtractStatus, extract_text
from aido.pdf.hash import sha256_of_file
from aido.store.decisions import NewDecision, find_by_source_hash, insert_decision
from aido.store.persons import get_person_by_slug
from aido.store.taxonomy import get_category_by_slug, get_review_category
from aido.types import (
    ClassificationResult,
    DecisionStatus,
    RouteOutcome,
)

_log = logging.getLogger("aido.pipeline")


class PipelineOutcome(str, Enum):
    AUTO_FILED = "auto_filed"
    REVIEW = "review"
    DUPLICATE_SKIP = "duplicate_skip"
    FAILED = "failed"


class Pipeline:
    def __init__(
        self,
        *,
        conn: sqlite3.Connection,
        classifier: Classifier,
        threshold: float,
        mutations: MutationContext,
        classifier_model: str,
        stabilize_seconds: float = 2.0,
    ) -> None:
        self._conn = conn
        self._classifier = classifier
        self._threshold = threshold
        self._mutations = mutations
        self._model = classifier_model
        self._stabilize = stabilize_seconds

    def process(self, src: Path) -> PipelineOutcome:
        try:
            return self._process(src)
        except Exception:
            _log.exception("pipeline.crashed", extra={"source_path": str(src)})
            return PipelineOutcome.FAILED

    def _process(self, src: Path) -> PipelineOutcome:
        self._wait_until_stable(src)
        if not src.exists():
            _log.warning("pipeline.source_missing", extra={"source_path": str(src)})
            return PipelineOutcome.FAILED

        source_hash = sha256_of_file(src)
        if find_by_source_hash(self._conn, source_hash) is not None:
            _log.info("pipeline.duplicate_skip",
                      extra={"source_path": str(src), "source_hash": source_hash})
            src.unlink(missing_ok=True)
            return PipelineOutcome.DUPLICATE_SKIP

        text, status = extract_text(src)
        if status is not ExtractStatus.OK:
            return self._route_to_review_no_classify(
                src,
                source_hash=source_hash,
                reason=status.value,
            )

        try:
            result = self._classifier.classify(text=text, original_filename=src.name)
        except Exception as exc:
            _log.exception("pipeline.classifier_failed",
                           extra={"source_hash": source_hash, "error": str(exc)})
            return self._route_to_review_no_classify(
                src,
                source_hash=source_hash,
                reason=f"classifier_error: {exc}",
            )

        decision = route(self._conn, result, threshold=self._threshold)
        target = self._build_target(decision, result)
        dest = file_document(src, archive_root=self._mutations.archive_root, target=target)

        new_id = self._record_decision(
            source_hash=source_hash,
            source_path=src,
            filed_path=dest,
            result=result,
            decision=decision,
        )
        _log.info(
            "pipeline.filed",
            extra={
                "decision_id": new_id,
                "source_hash": source_hash,
                "outcome": decision.outcome.value,
                "filed_path": str(dest),
                "model": self._model,
            },
        )
        return (
            PipelineOutcome.AUTO_FILED
            if decision.outcome is RouteOutcome.AUTO_FILE
            else PipelineOutcome.REVIEW
        )

    # ------------------------------------------------------------------
    # Helpers

    def _wait_until_stable(self, path: Path) -> None:
        if self._stabilize <= 0:
            return
        try:
            last_size = -1
            while True:
                size = path.stat().st_size
                if size == last_size:
                    return
                last_size = size
                time.sleep(self._stabilize)
        except FileNotFoundError:
            return

    def _build_target(
        self, decision: RouteDecision, result: ClassificationResult
    ) -> FilingTarget:
        if decision.outcome is RouteOutcome.AUTO_FILE:
            assert decision.person_id is not None
            assert decision.category_id is not None
            person_slug = self._slug_of_person(decision.person_id)
            cat_slug = self._slug_of_category(decision.category_id)
            return FilingTarget(
                person_slug=person_slug,
                category_slug=cat_slug,
                filename=result.proposed_filename,
            )
        # REVIEW path → top-level _review/
        review_cat = get_review_category(self._conn)
        assert review_cat is not None
        return FilingTarget(
            person_slug=None,
            category_slug=review_cat.slug,
            filename=result.proposed_filename,
        )

    def _route_to_review_no_classify(
        self, src: Path, *, source_hash: str, reason: str
    ) -> PipelineOutcome:
        """Path used when text extraction or classification fails BEFORE we
        have a ClassificationResult. We still record a decision row pointing
        to the file in _review/.
        """
        review_cat = get_review_category(self._conn)
        assert review_cat is not None, "DB missing _review category"
        filename = f"{datetime.now(timezone.utc).date().isoformat()}_uncertain_{source_hash[:8]}.pdf"
        dest = file_document(
            src,
            archive_root=self._mutations.archive_root,
            target=FilingTarget(
                person_slug=None, category_slug=review_cat.slug, filename=filename
            ),
        )
        # Need a person_id to satisfy FK; use 'shared' if it exists, else any active person.
        person = get_person_by_slug(self._conn, "shared") or self._any_person()
        if person is None:
            _log.error("pipeline.no_person_for_review",
                       extra={"source_hash": source_hash, "reason": reason})
            return PipelineOutcome.FAILED
        with self._conn:
            insert_decision(
                self._conn,
                NewDecision(
                    created_at=self._mutations.now(),
                    source_hash=source_hash,
                    source_path=str(src),
                    filed_path=str(dest),
                    person_id=person.id,
                    category_id=review_cat.id,
                    doctype_id=None,
                    document_date=None,
                    counterparty=None,
                    proposed_filename=filename,
                    overall_confidence=0.0,
                    person_confidence=0.0,
                    category_confidence=0.0,
                    reasoning=reason,
                    classifier_model=self._model,
                    new_category_proposal=None,
                    needs_review=True,
                    status=DecisionStatus.REVIEW,
                ),
            )
        return PipelineOutcome.REVIEW

    def _record_decision(
        self,
        *,
        source_hash: str,
        source_path: Path,
        filed_path: Path,
        result: ClassificationResult,
        decision: RouteDecision,
    ) -> int:
        needs_review = decision.outcome is RouteOutcome.REVIEW
        status = (
            DecisionStatus.AUTO_FILED
            if decision.outcome is RouteOutcome.AUTO_FILE
            else DecisionStatus.REVIEW
        )
        reasoning = result.reasoning
        if decision.reason is not None:
            reasoning = f"[{decision.reason.value}] {reasoning}"
        # If person/category id couldn't be resolved (unknown_person etc.),
        # we need to satisfy FK with something — use a fallback person.
        person_id = decision.person_id
        if person_id is None:
            person = get_person_by_slug(self._conn, "shared") or self._any_person()
            assert person is not None, "DB has no persons; run 'aido init'"
            person_id = person.id
        category_id = decision.category_id
        assert category_id is not None  # routing always returns at least _review.id
        with self._conn:
            return insert_decision(
                self._conn,
                NewDecision(
                    created_at=self._mutations.now(),
                    source_hash=source_hash,
                    source_path=str(source_path),
                    filed_path=str(filed_path),
                    person_id=person_id,
                    category_id=category_id,
                    doctype_id=decision.doctype_id,
                    document_date=result.document_date,
                    counterparty=result.counterparty or None,
                    proposed_filename=result.proposed_filename,
                    overall_confidence=result.overall_confidence,
                    person_confidence=result.person_confidence,
                    category_confidence=result.category_confidence,
                    reasoning=reasoning,
                    classifier_model=self._model,
                    new_category_proposal=result.new_category_proposal,
                    needs_review=needs_review,
                    status=status,
                ),
            )

    def _slug_of_person(self, person_id: int) -> str:
        row = self._conn.execute(
            "SELECT slug FROM persons WHERE id = ?", (person_id,)
        ).fetchone()
        assert row is not None
        return row["slug"]

    def _slug_of_category(self, category_id: int) -> str:
        row = self._conn.execute(
            "SELECT slug FROM categories WHERE id = ?", (category_id,)
        ).fetchone()
        assert row is not None
        return row["slug"]

    def _any_person(self):
        from aido.store.persons import list_persons
        persons = list_persons(self._conn)
        return persons[0] if persons else None
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/unit/test_pipeline.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/aido/worker/pipeline.py tests/unit/test_pipeline.py
git commit -m "feat(worker): add Pipeline.process orchestrating the full per-doc flow"
```

---

## Task 22: File watcher (PollingObserver)

**Files:**
- Create: `src/aido/worker/watcher.py`
- Test: `tests/integration/test_watcher.py`

Pinned to `PollingObserver` because Linux inotify inside a container doesn't see events on macOS-bind-mounted host paths. Polling every 2s is the spec's documented behaviour (§8.7).

- [ ] **Step 1: Write failing test**

```python
# tests/integration/test_watcher.py
import time
from pathlib import Path

import pytest

from aido.worker.queue import InboxQueue
from aido.worker.watcher import InboxWatcher


def _wait_for(predicate, timeout=5.0, interval=0.1):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def test_watcher_picks_up_new_pdf(tmp_path: Path):
    q = InboxQueue()
    watcher = InboxWatcher(inbox=tmp_path, queue=q, poll_interval=0.2)
    watcher.start()
    try:
        # Drop a PDF after the watcher is running.
        target = tmp_path / "new.pdf"
        target.write_bytes(b"%PDF-1.4\n%fake\n")
        assert _wait_for(lambda: q.get(timeout=0.1) is not None or False, timeout=4.0) or \
            _wait_for(lambda: target.exists() and q._q.qsize() >= 1, timeout=4.0)  # type: ignore[attr-defined]
    finally:
        watcher.stop()


def test_watcher_ignores_non_pdfs(tmp_path: Path):
    q = InboxQueue()
    watcher = InboxWatcher(inbox=tmp_path, queue=q, poll_interval=0.2)
    watcher.start()
    try:
        (tmp_path / "note.txt").write_text("hi")
        time.sleep(1.0)
        assert q.get(timeout=0.1) is None
    finally:
        watcher.stop()


def test_watcher_ignores_hidden_files(tmp_path: Path):
    q = InboxQueue()
    watcher = InboxWatcher(inbox=tmp_path, queue=q, poll_interval=0.2)
    watcher.start()
    try:
        (tmp_path / ".hidden.pdf").write_bytes(b"%PDF-1.4")
        time.sleep(1.0)
        assert q.get(timeout=0.1) is None
    finally:
        watcher.stop()
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/integration/test_watcher.py -v`
Expected: import errors.

- [ ] **Step 3: Implement `src/aido/worker/watcher.py`**

```python
"""Watchdog-based file watcher that pushes PDFs to an InboxQueue.

We pin to `PollingObserver` because the daemon runs in a Docker container on
macOS where host bind-mounts do not emit inotify events.
"""
from __future__ import annotations

import logging
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers.polling import PollingObserver

from aido.worker.queue import InboxQueue

_log = logging.getLogger("aido.watcher")


def _is_pdf(path: Path) -> bool:
    return (
        path.is_file()
        and not path.name.startswith(".")
        and path.suffix.lower() == ".pdf"
    )


class _Handler(FileSystemEventHandler):
    def __init__(self, queue: InboxQueue) -> None:
        self._queue = queue

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if _is_pdf(path):
            _log.info("watcher.enqueue", extra={"source_path": str(path)})
            self._queue.put(path)

    def on_moved(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = Path(event.dest_path)
        if _is_pdf(path):
            _log.info("watcher.enqueue", extra={"source_path": str(path)})
            self._queue.put(path)


class InboxWatcher:
    """Run a PollingObserver against `inbox`, enqueueing new PDFs."""

    def __init__(self, *, inbox: Path, queue: InboxQueue, poll_interval: float = 2.0) -> None:
        self._inbox = inbox
        self._queue = queue
        self._observer = PollingObserver(timeout=poll_interval)
        self._handler = _Handler(queue)

    def start(self) -> None:
        self._inbox.mkdir(parents=True, exist_ok=True)
        self._observer.schedule(self._handler, str(self._inbox), recursive=False)
        self._observer.start()

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join(timeout=5)
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/integration/test_watcher.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/aido/worker/watcher.py tests/integration/test_watcher.py
git commit -m "feat(worker): add InboxWatcher (PollingObserver) for macOS bind mounts"
```

---

## Task 23: Daemon main loop, healthz state, pidfile

**Files:**
- Create: `src/aido/daemon.py`
- Test: `tests/integration/test_daemon_lifecycle.py`

`Daemon.run()` wires watcher + queue + pipeline + classifier and loops until SIGTERM. Exposes a thread-safe `HealthState` object the web UI reads.

- [ ] **Step 1: Write failing test**

```python
# tests/integration/test_daemon_lifecycle.py
import time
from datetime import date
from pathlib import Path

import pytest

from aido.classifier.fake import FakeClassifier
from aido.daemon import Daemon, HealthStatus
from aido.store.connection import connect
from aido.store.decisions import find_by_source_hash
from aido.store.migrations import init_db
from aido.store.persons import create_person
from aido.store.taxonomy import create_category, create_doctype
from aido.types import ClassificationResult
from tests.fixtures import synth_pdf


def _result():
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
        reasoning="r",
    )


@pytest.fixture
def seeded(tmp_path):
    archive = tmp_path / "archive"
    inbox = tmp_path / "inbox"
    archive.mkdir()
    inbox.mkdir()
    db = tmp_path / "x.sqlite"
    with connect(db) as conn:
        init_db(conn)
        create_person(conn, slug="timo", display_name="Timo Jakob")
        create_person(conn, slug="shared", display_name="Shared", is_shared=True)
        create_category(conn, slug="rechnungen", display_name="Rechnungen")
        create_category(conn, slug="_review", display_name="_review", is_review=True)
        create_doctype(conn, slug="rechnung", display_name="Rechnung")
        create_doctype(conn, slug="letter", display_name="Letter")
    return {"db": db, "archive": archive, "inbox": inbox, "tmp": tmp_path}


def test_daemon_files_a_pdf_dropped_in_inbox(seeded):
    fake = FakeClassifier(results=[_result()])
    daemon = Daemon(
        db_path=seeded["db"],
        archive_root=seeded["archive"],
        inbox=seeded["inbox"],
        classifier_factory=lambda conn: fake,
        threshold=0.75,
        classifier_model="claude-opus-4-7",
        poll_interval=0.2,
        stabilize_seconds=0.0,
        pidfile=seeded["tmp"] / "aido.pid",
    )
    daemon.start()
    try:
        pdf = synth_pdf(seeded["inbox"] / "scan001.pdf", text=["Telekom Rechnung"])
        # Wait up to 5s for the worker to file it.
        deadline = time.monotonic() + 5
        decision = None
        while time.monotonic() < deadline:
            with connect(seeded["db"]) as conn:
                from aido.pdf.hash import sha256_of_file
                if pdf.exists():
                    h = sha256_of_file(pdf)
                else:
                    # Already moved — scan archive folder for files
                    moved = list(seeded["archive"].rglob("*.pdf"))
                    if moved:
                        h = sha256_of_file(moved[0])
                    else:
                        h = ""
                if h:
                    decision = find_by_source_hash(conn, h)
                if decision is not None:
                    break
            time.sleep(0.2)
        assert decision is not None
        assert daemon.health.status == HealthStatus.OK
    finally:
        daemon.stop()


def test_daemon_pidfile_prevents_double_start(seeded):
    daemon1 = Daemon(
        db_path=seeded["db"],
        archive_root=seeded["archive"],
        inbox=seeded["inbox"],
        classifier_factory=lambda conn: FakeClassifier(results=[]),
        threshold=0.75,
        classifier_model="m",
        pidfile=seeded["tmp"] / "aido.pid",
        poll_interval=0.5,
    )
    daemon1.start()
    try:
        daemon2 = Daemon(
            db_path=seeded["db"],
            archive_root=seeded["archive"],
            inbox=seeded["inbox"],
            classifier_factory=lambda conn: FakeClassifier(results=[]),
            threshold=0.75,
            classifier_model="m",
            pidfile=seeded["tmp"] / "aido.pid",
            poll_interval=0.5,
        )
        with pytest.raises(RuntimeError, match="already running"):
            daemon2.start()
    finally:
        daemon1.stop()
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/integration/test_daemon_lifecycle.py -v`
Expected: module missing.

- [ ] **Step 3: Implement `src/aido/daemon.py`**

```python
"""aido daemon: wires watcher + queue + worker + classifier; tracks health."""
from __future__ import annotations

import logging
import os
import signal
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable

from aido.classifier.base import Classifier
from aido.mutations import MutationContext
from aido.store.connection import connect
from aido.store.migrations import init_db
from aido.worker.pipeline import Pipeline, PipelineOutcome
from aido.worker.queue import InboxQueue
from aido.worker.watcher import InboxWatcher

_log = logging.getLogger("aido.daemon")


class HealthStatus(str, Enum):
    OK = "ok"
    AUTH_FAILED = "auth_failed"
    CANNOT_WRITE = "cannot_write"
    DEGRADED = "degraded"


@dataclass
class HealthState:
    status: HealthStatus = HealthStatus.OK
    last_classification_at: datetime | None = None
    consecutive_failures: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record_outcome(self, outcome: PipelineOutcome, *, now: datetime) -> None:
        with self._lock:
            if outcome in (PipelineOutcome.AUTO_FILED, PipelineOutcome.REVIEW):
                self.consecutive_failures = 0
                self.last_classification_at = now
                if self.status == HealthStatus.DEGRADED:
                    self.status = HealthStatus.OK
            elif outcome == PipelineOutcome.FAILED:
                self.consecutive_failures += 1
                if self.consecutive_failures >= 3:
                    self.status = HealthStatus.DEGRADED

    def set(self, status: HealthStatus) -> None:
        with self._lock:
            self.status = status


class Daemon:
    """Long-running coordinator. `start()` spawns threads; `stop()` joins them."""

    def __init__(
        self,
        *,
        db_path: Path,
        archive_root: Path,
        inbox: Path,
        classifier_factory: Callable[[sqlite3.Connection], Classifier],
        threshold: float,
        classifier_model: str,
        pidfile: Path,
        poll_interval: float = 2.0,
        stabilize_seconds: float = 2.0,
    ) -> None:
        self._db_path = db_path
        self._archive_root = archive_root
        self._inbox = inbox
        self._classifier_factory = classifier_factory
        self._threshold = threshold
        self._classifier_model = classifier_model
        self._pidfile = pidfile
        self._poll_interval = poll_interval
        self._stabilize_seconds = stabilize_seconds

        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._watcher: InboxWatcher | None = None
        self._queue = InboxQueue()
        self.health = HealthState()
        self._conn: sqlite3.Connection | None = None
        self._mutations: MutationContext | None = None

    # ---- lifecycle ----------------------------------------------------

    def _acquire_pidfile(self) -> None:
        if self._pidfile.exists():
            try:
                pid = int(self._pidfile.read_text().strip())
            except ValueError:
                pid = -1
            if pid > 0 and _process_alive(pid):
                raise RuntimeError(f"aido already running (pid {pid})")
        self._pidfile.parent.mkdir(parents=True, exist_ok=True)
        self._pidfile.write_text(str(os.getpid()))

    def _release_pidfile(self) -> None:
        try:
            self._pidfile.unlink(missing_ok=True)
        except OSError:
            pass

    def start(self) -> None:
        self._acquire_pidfile()
        self._archive_root.mkdir(parents=True, exist_ok=True)
        self._inbox.mkdir(parents=True, exist_ok=True)
        ctx = connect(self._db_path)
        self._conn = ctx.__enter__()
        self._connection_ctx = ctx
        init_db(self._conn)

        self._mutations = MutationContext(
            conn=self._conn,
            archive_root=self._archive_root,
            lock=threading.Lock(),
            now=lambda: datetime.now(timezone.utc),
        )

        classifier = self._classifier_factory(self._conn)
        pipeline = Pipeline(
            conn=self._conn,
            classifier=classifier,
            threshold=self._threshold,
            mutations=self._mutations,
            classifier_model=self._classifier_model,
            stabilize_seconds=self._stabilize_seconds,
        )

        self._queue.drain_existing(self._inbox)
        self._watcher = InboxWatcher(inbox=self._inbox, queue=self._queue,
                                     poll_interval=self._poll_interval)
        self._watcher.start()

        self._worker_thread = threading.Thread(
            target=self._worker_loop, args=(pipeline,), daemon=True, name="aido-worker"
        )
        self._worker_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._watcher is not None:
            self._watcher.stop()
        if self._worker_thread is not None:
            self._worker_thread.join(timeout=10)
        if self._conn is not None:
            try:
                self._connection_ctx.__exit__(None, None, None)
            finally:
                self._conn = None
        self._release_pidfile()

    def install_signal_handlers(self) -> None:
        def _handler(signum, frame):
            _log.info("daemon.sigterm", extra={"signum": signum})
            self.stop()
        signal.signal(signal.SIGTERM, _handler)
        signal.signal(signal.SIGINT, _handler)

    # ---- worker loop --------------------------------------------------

    def _worker_loop(self, pipeline: Pipeline) -> None:
        while not self._stop_event.is_set():
            path = self._queue.get(timeout=0.5)
            if path is None:
                continue
            outcome = pipeline.process(path)
            self.health.record_outcome(outcome, now=datetime.now(timezone.utc))


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/integration/test_daemon_lifecycle.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/aido/daemon.py tests/integration/test_daemon_lifecycle.py
git commit -m "feat(daemon): add lifecycle, pidfile, and HealthState"
```

---

## Task 24: `aido init` CLI (with `--seed` non-interactive path)

**Files:**
- Create: `src/aido/cli.py`
- Create: `src/aido/__main__.py`
- Test: `tests/integration/test_cli_init.py`

`aido init` seeds the DB. With `--seed seed.yaml` it reads the data; without it, it walks the user through 4 family members + a starter taxonomy via `input()`. Default taxonomy is the German starter list from the spec.

- [ ] **Step 1: Write failing test**

```python
# tests/integration/test_cli_init.py
from pathlib import Path

import pytest

from aido.cli import main as cli_main
from aido.store.connection import connect
from aido.store.persons import find_person_by_alias, list_persons
from aido.store.taxonomy import (
    get_category_by_slug,
    get_doctype_by_slug,
    get_review_category,
    list_categories,
)


def test_init_with_seed_file(tmp_path: Path):
    db = tmp_path / "aido.sqlite"
    seed = tmp_path / "seed.yaml"
    seed.write_text(
        """
persons:
  - slug: timo
    display_name: Timo Jakob
    aliases: [Timo Jakob, T. Jakob, Jakob]
  - slug: anna
    display_name: Anna Jakob
    aliases: [Anna Jakob]
  - slug: penelope
    display_name: Pénélope Müller
    aliases: [Penelope, Penélope, Müller]
  - slug: child2
    display_name: Lea Jakob
    aliases: [Lea Jakob]
  - slug: shared
    display_name: Shared
    is_shared: true
    aliases: []

categories:
  - slug: rechnungen
    display_name: Rechnungen
  - slug: steuer
    display_name: Steuer
  - slug: medizin
    display_name: Medizin
  - slug: vertraege
    display_name: Verträge

doctypes:
  - slug: rechnung
    display_name: Rechnung
  - slug: letter
    display_name: Brief
""".strip(),
        encoding="utf-8",
    )
    rc = cli_main(["init", "--db", str(db), "--seed", str(seed)])
    assert rc == 0
    with connect(db) as conn:
        slugs = {p.slug for p in list_persons(conn)}
        assert slugs == {"timo", "anna", "penelope", "child2", "shared"}
        # Aliases were inserted and are case/accent-insensitive.
        assert find_person_by_alias(conn, "penelope") is not None
        assert find_person_by_alias(conn, "Penélope") is not None
        # Categories include the user's list + the _review row that init adds automatically.
        cat_slugs = {c.slug for c in list_categories(conn, include_inactive=True)}
        assert "_review" in cat_slugs
        assert {"rechnungen", "steuer", "medizin", "vertraege"} <= cat_slugs
        assert get_review_category(conn) is not None
        assert get_doctype_by_slug(conn, "rechnung") is not None


def test_init_is_idempotent(tmp_path: Path):
    db = tmp_path / "aido.sqlite"
    seed = tmp_path / "seed.yaml"
    seed.write_text(
        """
persons:
  - slug: timo
    display_name: Timo
    aliases: [Timo]
categories: []
doctypes: []
""".strip(),
        encoding="utf-8",
    )
    rc1 = cli_main(["init", "--db", str(db), "--seed", str(seed)])
    rc2 = cli_main(["init", "--db", str(db), "--seed", str(seed)])
    assert rc1 == 0 and rc2 == 0  # second run must not raise
    with connect(db) as conn:
        slugs = [p.slug for p in list_persons(conn)]
        assert slugs == ["timo"]  # not duplicated


def test_init_creates_archive_and_inbox_paths(tmp_path: Path, monkeypatch):
    db = tmp_path / "aido.sqlite"
    archive = tmp_path / "archive"
    inbox = tmp_path / "inbox"
    seed = tmp_path / "seed.yaml"
    seed.write_text("persons: []\ncategories: []\ndoctypes: []\n", encoding="utf-8")
    rc = cli_main([
        "init",
        "--db", str(db),
        "--seed", str(seed),
        "--archive-root", str(archive),
        "--scan-inbox", str(inbox),
    ])
    assert rc == 0
    assert archive.exists()
    assert inbox.exists()
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/integration/test_cli_init.py -v`
Expected: module missing.

- [ ] **Step 3: Implement `src/aido/cli.py`**

```python
"""aido command-line interface.

Subcommands:
- init: bootstrap the DB (persons, aliases, categories, doctypes).
- status: print health + counts.
- rebuild-index: scan the archive directory and reconcile decisions table.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from ruamel.yaml import YAML

from aido.store.connection import connect
from aido.store.migrations import init_db
from aido.store.persons import add_alias, create_person, get_person_by_slug
from aido.store.taxonomy import (
    create_category,
    create_doctype,
    get_category_by_slug,
    get_doctype_by_slug,
)

_DEFAULT_CATEGORIES = [
    ("rechnungen", "Rechnungen", "Eingehende Rechnungen aller Art"),
    ("steuer", "Steuer", "Steuerbescheide, Steuererklärungen, Schreiben vom Finanzamt"),
    ("medizin", "Medizin", "Arztbriefe, Befunde, Rezepte"),
    ("vertraege", "Verträge", "Verträge und Vertragsänderungen"),
    ("bank", "Bank", "Kontoauszüge, Bankschreiben"),
    ("versicherung", "Versicherung", "Policen, Schadensmeldungen"),
    ("nebenkosten", "Nebenkosten", "Strom, Wasser, Gas, Müll"),
    ("briefe", "Briefe", "Allgemeine Korrespondenz"),
    ("schule", "Schule", "Zeugnisse, Elternbriefe, Schultermine"),
]

_DEFAULT_DOCTYPES = [
    ("rechnung", "Rechnung", "Eine Rechnung von einem Anbieter"),
    ("steuerbescheid", "Steuerbescheid", "Bescheid vom Finanzamt"),
    ("kontoauszug", "Kontoauszug", "Bank-Kontoauszug"),
    ("vertrag", "Vertrag", "Vertragsdokument"),
    ("versicherungs-schreiben", "Versicherungsschreiben", "Schreiben einer Versicherung"),
    ("arztbrief", "Arztbrief", "Schreiben eines Arztes oder Krankenhauses"),
    ("zeugnis", "Zeugnis", "Schulzeugnis"),
    ("letter", "Brief", "Allgemeines Schreiben (Fallback)"),
]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aido")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="bootstrap the DB and archive folders")
    p_init.add_argument("--db", type=Path, required=True)
    p_init.add_argument("--seed", type=Path, help="YAML seed file (non-interactive)")
    p_init.add_argument("--archive-root", type=Path,
                        help="create this directory if missing")
    p_init.add_argument("--scan-inbox", type=Path,
                        help="create this directory if missing")

    p_status = sub.add_parser("status", help="print health and queue counts")
    p_status.add_argument("--db", type=Path, required=True)

    p_reindex = sub.add_parser(
        "rebuild-index",
        help="scan the archive and reconcile (no-op placeholder for v1)",
    )
    p_reindex.add_argument("--db", type=Path, required=True)

    args = parser.parse_args(argv)

    if args.cmd == "init":
        return _cmd_init(args)
    if args.cmd == "status":
        return _cmd_status(args)
    if args.cmd == "rebuild-index":
        # v1: keep a no-op stub; real reconciliation lands in a follow-up.
        print("rebuild-index: no-op placeholder for v1", file=sys.stderr)
        return 0
    parser.error(f"unknown command: {args.cmd}")
    return 2  # unreachable


def _cmd_init(args: argparse.Namespace) -> int:
    if args.archive_root is not None:
        args.archive_root.mkdir(parents=True, exist_ok=True)
    if args.scan_inbox is not None:
        args.scan_inbox.mkdir(parents=True, exist_ok=True)

    with connect(args.db) as conn:
        init_db(conn)
        if args.seed is not None:
            _seed_from_yaml(conn, args.seed)
        else:
            _seed_interactive(conn)
        # Ensure the _review category always exists.
        if get_category_by_slug(conn, "_review") is None:
            with conn:
                create_category(
                    conn, slug="_review", display_name="_review", is_review=True
                )
        # Apply defaults for any missing categories/doctypes (no overwrite).
        with conn:
            for slug, name, desc in _DEFAULT_CATEGORIES:
                if get_category_by_slug(conn, slug) is None:
                    create_category(conn, slug=slug, display_name=name, description=desc)
            for slug, name, desc in _DEFAULT_DOCTYPES:
                if get_doctype_by_slug(conn, slug) is None:
                    create_doctype(conn, slug=slug, display_name=name, description=desc)
    print(f"init: db ready at {args.db}")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    from aido.store.decisions import count_needs_review
    with connect(args.db) as conn:
        n = count_needs_review(conn)
    print(f"needs_review: {n}")
    return 0


def _seed_from_yaml(conn, seed_path: Path) -> None:
    yaml = YAML(typ="safe")
    data = yaml.load(seed_path.read_text(encoding="utf-8")) or {}
    with conn:
        for entry in data.get("persons", []) or []:
            slug = entry["slug"]
            if get_person_by_slug(conn, slug) is not None:
                continue
            person = create_person(
                conn,
                slug=slug,
                display_name=entry["display_name"],
                is_shared=bool(entry.get("is_shared", False)),
            )
            for alias in entry.get("aliases", []) or []:
                add_alias(conn, person_id=person.id, alias=alias)
        for entry in data.get("categories", []) or []:
            slug = entry["slug"]
            if get_category_by_slug(conn, slug) is None:
                create_category(
                    conn,
                    slug=slug,
                    display_name=entry["display_name"],
                    description=entry.get("description"),
                    is_review=bool(entry.get("is_review", False)),
                )
        for entry in data.get("doctypes", []) or []:
            slug = entry["slug"]
            if get_doctype_by_slug(conn, slug) is None:
                create_doctype(
                    conn,
                    slug=slug,
                    display_name=entry["display_name"],
                    description=entry.get("description"),
                )


def _seed_interactive(conn) -> None:
    print("Interactive init: configure four family members + a shared bucket.\n"
          "You can run this again later, or use --seed seed.yaml for non-interactive setup.")
    with conn:
        for i in range(1, 5):
            slug = input(f"Person {i} slug (e.g. 'timo'): ").strip()
            if not slug:
                continue
            if get_person_by_slug(conn, slug) is not None:
                print(f"  skipping {slug} (already exists)")
                continue
            display = input(f"  Display name for {slug}: ").strip() or slug
            person = create_person(conn, slug=slug, display_name=display)
            raw_aliases = input(f"  Aliases for {slug} (comma-separated): ").strip()
            for alias in (a.strip() for a in raw_aliases.split(",") if a.strip()):
                add_alias(conn, person_id=person.id, alias=alias)
        if get_person_by_slug(conn, "shared") is None:
            create_person(conn, slug="shared", display_name="Shared", is_shared=True)
            print("  added shared bucket")


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Implement `src/aido/__main__.py`**

```python
"""Module entrypoint so `python -m aido` works."""
from __future__ import annotations

import sys

from aido.cli import main

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run tests, verify pass**

Run: `pytest tests/integration/test_cli_init.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add src/aido/cli.py src/aido/__main__.py tests/integration/test_cli_init.py
git commit -m "feat(cli): add aido init/status/rebuild-index with --seed support"
```

---

## Task 25: Flask app factory + base template

**Files:**
- Create: `src/aido/webui/app.py`
- Create: `src/aido/webui/templates/base.html`
- Create: `src/aido/webui/static/app.js`
- Test: `tests/integration/test_webui_feed.py` (smoke test only here; populated in Task 26)

`create_app(daemon_state)` returns a Flask app pre-configured with the daemon's DB connection, archive root, mutation context, and health state. Templates inherit from `base.html`.

- [ ] **Step 1: Write failing test (smoke only)**

```python
# tests/integration/test_webui_feed.py
from datetime import date

import pytest

from aido.webui.app import create_app, WebState


@pytest.fixture
def web(tmp_path):
    from aido.store.connection import connect
    from aido.store.migrations import init_db
    from aido.store.persons import create_person
    from aido.store.taxonomy import create_category, create_doctype
    import threading
    from aido.mutations import MutationContext
    archive = tmp_path / "archive"
    archive.mkdir()
    db = tmp_path / "x.sqlite"
    with connect(db) as conn:
        init_db(conn)
        create_person(conn, slug="timo", display_name="Timo Jakob")
        create_category(conn, slug="rechnungen", display_name="Rechnungen")
        create_category(conn, slug="_review", display_name="_review", is_review=True)
        create_doctype(conn, slug="rechnung", display_name="Rechnung")
        from aido.daemon import HealthState
        state = WebState(
            db_path=db,
            archive_root=archive,
            mutations=MutationContext(
                conn=conn, archive_root=archive, lock=threading.Lock(),
                now=lambda: __import__("datetime").datetime.now(),
            ),
            health=HealthState(),
        )
        app = create_app(state)
        app.config["TESTING"] = True
        yield app.test_client()


def test_index_renders(web):
    rv = web.get("/")
    assert rv.status_code == 200
    # Base layout markers we'll add in Task 25.
    assert b"aido" in rv.data


def test_healthz_returns_json(web):
    rv = web.get("/healthz")
    assert rv.status_code == 200
    assert rv.is_json
    body = rv.get_json()
    assert body["status"] == "ok"
    assert "needs_review" in body
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/integration/test_webui_feed.py -v`
Expected: module missing.

- [ ] **Step 3: Implement `src/aido/webui/app.py`**

```python
"""Flask app factory for the retro-audit web UI."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from flask import Flask, jsonify, render_template

from aido.daemon import HealthState
from aido.mutations import MutationContext
from aido.store.connection import connect
from aido.store.decisions import count_needs_review


@dataclass
class WebState:
    db_path: Path
    archive_root: Path
    mutations: MutationContext
    health: HealthState


def create_app(state: WebState) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["AIDO_STATE"] = state

    @app.route("/")
    def index() -> str:
        # Real feed is implemented in Task 26; for now show the shell.
        with connect(state.db_path) as conn:
            pending = count_needs_review(conn)
        return render_template("base.html", needs_review_count=pending,
                               health=state.health.status.value)

    @app.route("/healthz")
    def healthz():
        with connect(state.db_path) as conn:
            pending = count_needs_review(conn)
        return jsonify(
            {
                "status": state.health.status.value,
                "needs_review": pending,
                "last_classification_at": (
                    state.health.last_classification_at.isoformat()
                    if state.health.last_classification_at
                    else None
                ),
            }
        )

    return app
```

- [ ] **Step 4: Implement `src/aido/webui/templates/base.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>aido — household document organizer</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='app.css') }}">
</head>
<body>
  <header class="topbar">
    <span class="brand">aido</span>
    <nav>
      <a href="{{ url_for('index') }}">Recently filed</a>
      <a href="/needs-review">
        Needs review
        {% if needs_review_count and needs_review_count > 0 %}
          <span class="badge">{{ needs_review_count }}</span>
        {% endif %}
      </a>
      <a href="/all">All</a>
      <a href="/settings">Settings</a>
      <a href="/stats">Stats</a>
    </nav>
    <span class="health" data-health="{{ health }}">{{ health }}</span>
  </header>
  <main>{% block body %}{% endblock %}</main>
  <script src="{{ url_for('static', filename='app.js') }}" defer></script>
</body>
</html>
```

- [ ] **Step 5: Implement `src/aido/webui/static/app.js`** (and `app.css`)

`src/aido/webui/static/app.js`:
```js
// Minimal helpers. Real interaction lives in templates' inline scripts.
window.aido = {
  postJSON: async function (url, body) {
    const r = await fetch(url, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      const text = await r.text();
      throw new Error(`POST ${url} failed: ${r.status} ${text}`);
    }
    return r.json();
  },
};
```

`src/aido/webui/static/app.css`:
```css
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       margin: 0; background: #0f172a; color: #e5e7eb; }
.topbar { display: flex; align-items: center; gap: 1rem; padding: .75rem 1.25rem;
          background: #1f2937; border-bottom: 1px solid #374151; }
.topbar .brand { font-weight: 700; }
.topbar nav a { margin-right: 1rem; color: #cbd5e1; text-decoration: none; }
.topbar nav a:hover { color: #fff; }
.badge { display: inline-block; padding: 0 .4rem; border-radius: 999px;
         background: #ef4444; color: #fff; font-size: .75rem; margin-left: .25rem; }
.health { margin-left: auto; font-size: .8rem; color: #9ca3af; }
.health[data-health="ok"]::before { content: "● "; color: #34d399; }
.health[data-health="degraded"]::before { content: "● "; color: #f59e0b; }
.health[data-health="auth_failed"]::before,
.health[data-health="cannot_write"]::before { content: "● "; color: #ef4444; }
main { padding: 1rem 1.25rem; }
```

- [ ] **Step 6: Run tests, verify pass**

Run: `pytest tests/integration/test_webui_feed.py -v`
Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add src/aido/webui/
git commit -m "feat(webui): add Flask factory, base layout, /healthz"
```

---

## Task 26: Feed routes (Recently filed / Needs review / All)

**Files:**
- Create: `src/aido/webui/routes.py`
- Create: `src/aido/webui/templates/feed.html`
- Modify: `src/aido/webui/app.py` to register `routes` blueprint
- Extend test: `tests/integration/test_webui_feed.py`

- [ ] **Step 1: Extend the test from Task 25**

Append to `tests/integration/test_webui_feed.py`:

```python
def test_needs_review_tab_shows_only_uncertain(web):
    # Drive through the daemon would be heavy; insert decisions directly.
    from datetime import datetime, timezone

    from aido.store.connection import connect
    from aido.store.decisions import NewDecision, insert_decision
    from aido.store.persons import get_person_by_slug
    from aido.store.taxonomy import get_category_by_slug, get_review_category
    from aido.types import DecisionStatus

    state = web.application.config["AIDO_STATE"]
    with connect(state.db_path) as conn:
        timo = get_person_by_slug(conn, "timo")
        cat = get_category_by_slug(conn, "rechnungen")
        review = get_review_category(conn)
        insert_decision(conn, NewDecision(
            created_at=datetime(2026, 5, 17, 10, tzinfo=timezone.utc),
            source_hash="h1", source_path="/s", filed_path="/a",
            person_id=timo.id, category_id=cat.id, doctype_id=None,
            document_date=None, counterparty="t",
            proposed_filename="x.pdf",
            overall_confidence=0.9, person_confidence=0.9, category_confidence=0.9,
            reasoning="confident", classifier_model="m",
            new_category_proposal=None, needs_review=False,
            status=DecisionStatus.AUTO_FILED,
        ))
        insert_decision(conn, NewDecision(
            created_at=datetime(2026, 5, 17, 11, tzinfo=timezone.utc),
            source_hash="h2", source_path="/s", filed_path="/a",
            person_id=timo.id, category_id=review.id, doctype_id=None,
            document_date=None, counterparty=None,
            proposed_filename="uncertain.pdf",
            overall_confidence=0.4, person_confidence=0.4, category_confidence=0.4,
            reasoning="hesitant", classifier_model="m",
            new_category_proposal=None, needs_review=True,
            status=DecisionStatus.REVIEW,
        ))

    rv_all = web.get("/all")
    assert rv_all.status_code == 200
    body = rv_all.get_data(as_text=True)
    assert "x.pdf" in body
    assert "uncertain.pdf" in body

    rv_review = web.get("/needs-review")
    body = rv_review.get_data(as_text=True)
    assert "uncertain.pdf" in body
    assert "x.pdf" not in body
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/integration/test_webui_feed.py -v`
Expected: 404 errors on /all and /needs-review.

- [ ] **Step 3: Implement `src/aido/webui/routes.py`**

```python
"""Feed routes: /, /needs-review, /all."""
from __future__ import annotations

from flask import Blueprint, current_app, render_template

from aido.store.connection import connect
from aido.store.decisions import count_needs_review, list_recent

bp = Blueprint("feed", __name__)


def _state():
    return current_app.config["AIDO_STATE"]


@bp.route("/")
def index() -> str:
    state = _state()
    with connect(state.db_path) as conn:
        decisions = list_recent(conn, limit=50)
        pending = count_needs_review(conn)
        rows = _hydrate(conn, decisions)
    return render_template(
        "feed.html",
        decisions=rows,
        title="Recently filed",
        needs_review_count=pending,
        health=state.health.status.value,
    )


@bp.route("/needs-review")
def needs_review() -> str:
    state = _state()
    with connect(state.db_path) as conn:
        decisions = list_recent(conn, limit=200, needs_review_only=True)
        pending = count_needs_review(conn)
        rows = _hydrate(conn, decisions)
    return render_template(
        "feed.html",
        decisions=rows,
        title="Needs review",
        needs_review_count=pending,
        health=state.health.status.value,
    )


@bp.route("/all")
def all_decisions() -> str:
    state = _state()
    with connect(state.db_path) as conn:
        decisions = list_recent(conn, limit=500)
        pending = count_needs_review(conn)
        rows = _hydrate(conn, decisions)
    return render_template(
        "feed.html",
        decisions=rows,
        title="All decisions",
        needs_review_count=pending,
        health=state.health.status.value,
    )


def _hydrate(conn, decisions):
    """Attach person and category slug to each row for display."""
    out = []
    for d in decisions:
        person = conn.execute(
            "SELECT slug, display_name FROM persons WHERE id = ?", (d.person_id,)
        ).fetchone()
        cat = conn.execute(
            "SELECT slug, display_name FROM categories WHERE id = ?", (d.category_id,)
        ).fetchone()
        out.append({
            "decision": d,
            "person_slug": person["slug"] if person else "?",
            "person_display": person["display_name"] if person else "?",
            "category_slug": cat["slug"] if cat else "?",
            "category_display": cat["display_name"] if cat else "?",
        })
    return out
```

- [ ] **Step 4: Update `src/aido/webui/app.py` to register the blueprint**

Replace the `index` and `healthz` inline route definitions in `app.py` with blueprint registration:

```python
# Replace the two inline routes inside create_app() with:
    from aido.webui.routes import bp as feed_bp
    app.register_blueprint(feed_bp)

    @app.route("/healthz")
    def healthz():
        with connect(state.db_path) as conn:
            pending = count_needs_review(conn)
        return jsonify({
            "status": state.health.status.value,
            "needs_review": pending,
            "last_classification_at": (
                state.health.last_classification_at.isoformat()
                if state.health.last_classification_at
                else None
            ),
        })
```

(Remove the old `def index()` that was in `app.py`; keep `healthz`.)

- [ ] **Step 5: Implement `src/aido/webui/templates/feed.html`**

```html
{% extends "base.html" %}
{% block body %}
<h2>{{ title }}</h2>
{% if decisions|length == 0 %}
  <p class="muted">Nothing here yet.</p>
{% else %}
<table class="feed">
  <thead>
    <tr>
      <th>When</th>
      <th>Filename</th>
      <th>Person</th>
      <th>Category</th>
      <th>Confidence</th>
      <th></th>
    </tr>
  </thead>
  <tbody>
  {% for row in decisions %}
    <tr class="{{ 'needs-review' if row.decision.needs_review else '' }}">
      <td>{{ row.decision.created_at.isoformat(sep=' ', timespec='minutes') }}</td>
      <td><code>{{ row.decision.proposed_filename }}</code></td>
      <td>{{ row.person_slug }}</td>
      <td>{{ row.category_slug }}</td>
      <td>
        {% if row.decision.needs_review %}
          <span class="conf rev">REVIEW {{ '%.2f' % row.decision.overall_confidence }}</span>
        {% else %}
          <span class="conf hi">{{ '%.2f' % row.decision.overall_confidence }}</span>
        {% endif %}
      </td>
      <td><a href="/decisions/{{ row.decision.id }}">open</a></td>
    </tr>
  {% endfor %}
  </tbody>
</table>
{% endif %}
{% endblock %}
```

Add to `app.css`:
```css
table.feed { width: 100%; border-collapse: collapse; }
table.feed th, table.feed td { padding: .35rem .6rem; border-bottom: 1px solid #1f2937; text-align: left; }
table.feed tr.needs-review { background: #1f29373d; }
.conf { display: inline-block; padding: 0 .4rem; border-radius: 4px;
        font-size: .75rem; font-weight: 600; }
.conf.hi { background: #064e3b; color: #6ee7b7; }
.conf.rev { background: #7f1d1d; color: #fca5a5; }
.muted { color: #9ca3af; }
a { color: #93c5fd; }
```

- [ ] **Step 6: Run tests, verify pass**

Run: `pytest tests/integration/test_webui_feed.py -v`
Expected: 3 passed (the original 2 + the new needs-review test).

- [ ] **Step 7: Commit**

```bash
git add src/aido/webui/
git commit -m "feat(webui): add feed routes (index / needs-review / all)"
```

---

## Task 27: Detail route + PDF preview iframe + stats page

**Files:**
- Modify: `src/aido/webui/routes.py` (add `/decisions/<id>`, `/pdf/<id>`, `/stats`)
- Create: `src/aido/webui/templates/detail.html`
- Create: `src/aido/webui/templates/stats.html`
- Test: `tests/integration/test_webui_detail.py`

`GET /decisions/<id>` renders the right-pane detail view with an `<iframe>` pointing at `/pdf/<id>`, which streams the file from disk. The detail page also includes the inline re-file form (handler in Task 28).

- [ ] **Step 1: Write failing test**

```python
# tests/integration/test_webui_detail.py
import threading
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from aido.daemon import HealthState
from aido.mutations import MutationContext
from aido.store.connection import connect
from aido.store.decisions import NewDecision, insert_decision
from aido.store.migrations import init_db
from aido.store.persons import create_person
from aido.store.taxonomy import create_category, create_doctype
from aido.types import DecisionStatus
from aido.webui.app import WebState, create_app


@pytest.fixture
def web(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    db = tmp_path / "x.sqlite"
    with connect(db) as conn:
        init_db(conn)
        timo = create_person(conn, slug="timo", display_name="Timo")
        cat = create_category(conn, slug="rechnungen", display_name="Rechnungen")
        create_category(conn, slug="_review", display_name="_review", is_review=True)
        dt = create_doctype(conn, slug="rechnung", display_name="Rechnung")
        filed = archive / "timo" / "rechnungen" / "2026-03-12_rechnung_telekom.pdf"
        filed.parent.mkdir(parents=True)
        filed.write_bytes(b"%PDF-1.4\n%pretend\n")
        new_id = insert_decision(conn, NewDecision(
            created_at=datetime(2026, 5, 17, 10, tzinfo=timezone.utc),
            source_hash="h1", source_path="/s/x.pdf", filed_path=str(filed),
            person_id=timo.id, category_id=cat.id, doctype_id=dt.id,
            document_date=date(2026, 3, 12), counterparty="telekom",
            proposed_filename="2026-03-12_rechnung_telekom.pdf",
            overall_confidence=0.93, person_confidence=0.95, category_confidence=0.91,
            reasoning="recipient Timo; sender Telekom",
            classifier_model="claude-opus-4-7",
            new_category_proposal=None, needs_review=False,
            status=DecisionStatus.AUTO_FILED,
        ))
    state = WebState(
        db_path=db,
        archive_root=archive,
        mutations=MutationContext(
            conn=None,  # webui doesn't reuse the worker's connection
            archive_root=archive,
            lock=threading.Lock(),
            now=lambda: datetime.now(timezone.utc),
        ),
        health=HealthState(),
    )
    app = create_app(state)
    app.config["TESTING"] = True
    return app.test_client(), new_id, filed


def test_detail_renders(web):
    client, new_id, _ = web
    rv = client.get(f"/decisions/{new_id}")
    assert rv.status_code == 200
    body = rv.get_data(as_text=True)
    assert "telekom" in body.lower()
    assert "sender Telekom" in body  # reasoning shown
    assert f'/pdf/{new_id}' in body  # iframe src present


def test_detail_404_for_unknown(web):
    client, _, _ = web
    assert client.get("/decisions/9999").status_code == 404


def test_pdf_route_streams_bytes(web):
    client, new_id, filed = web
    rv = client.get(f"/pdf/{new_id}")
    assert rv.status_code == 200
    assert rv.mimetype == "application/pdf"
    assert rv.data.startswith(b"%PDF-")


def test_pdf_route_404_when_file_missing(web):
    client, new_id, filed = web
    filed.unlink()
    assert client.get(f"/pdf/{new_id}").status_code == 404


def test_stats_renders(web):
    client, _, _ = web
    rv = client.get("/stats")
    assert rv.status_code == 200
    body = rv.get_data(as_text=True)
    assert "Stats" in body
    assert "needs_review" in body.lower() or "needs review" in body.lower()
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/integration/test_webui_detail.py -v`
Expected: 404s on the new routes.

- [ ] **Step 3: Extend `src/aido/webui/routes.py`**

Append to `routes.py`:

```python
from flask import abort, send_file

from aido.store.decisions import get_decision
from aido.store.persons import list_persons
from aido.store.taxonomy import list_categories


@bp.route("/decisions/<int:decision_id>")
def detail(decision_id: int) -> str:
    state = _state()
    with connect(state.db_path) as conn:
        d = get_decision(conn, decision_id)
        if d is None:
            abort(404)
        pending = count_needs_review(conn)
        person = conn.execute(
            "SELECT slug, display_name FROM persons WHERE id = ?", (d.person_id,)
        ).fetchone()
        cat = conn.execute(
            "SELECT slug, display_name FROM categories WHERE id = ?", (d.category_id,)
        ).fetchone()
        all_persons = list_persons(conn)
        all_categories = list_categories(conn)
    return render_template(
        "detail.html",
        decision=d,
        person_slug=person["slug"] if person else "?",
        category_slug=cat["slug"] if cat else "?",
        all_persons=all_persons,
        all_categories=all_categories,
        needs_review_count=pending,
        health=state.health.status.value,
    )


@bp.route("/pdf/<int:decision_id>")
def pdf(decision_id: int):
    state = _state()
    with connect(state.db_path) as conn:
        d = get_decision(conn, decision_id)
    if d is None:
        abort(404)
    from pathlib import Path
    p = Path(d.filed_path)
    if not p.exists():
        abort(404)
    return send_file(p, mimetype="application/pdf")


@bp.route("/stats")
def stats() -> str:
    state = _state()
    with connect(state.db_path) as conn:
        pending = count_needs_review(conn)
        total = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        last7 = conn.execute(
            "SELECT COUNT(*) FROM decisions WHERE created_at >= datetime('now', '-7 days')"
        ).fetchone()[0]
        avg_conf = conn.execute(
            "SELECT AVG(overall_confidence) FROM decisions WHERE status = 'auto_filed'"
        ).fetchone()[0]
    return render_template(
        "stats.html",
        total=total,
        last7=last7,
        avg_confidence=avg_conf or 0.0,
        needs_review_count=pending,
        health=state.health.status.value,
    )
```

- [ ] **Step 4: Implement `src/aido/webui/templates/detail.html`**

```html
{% extends "base.html" %}
{% block body %}
<div class="detail">
  <div class="preview">
    <iframe src="{{ url_for('feed.pdf', decision_id=decision.id) }}"
            title="PDF preview"></iframe>
    <p class="muted">
      Filename: <code>{{ decision.proposed_filename }}</code><br>
      Current path: <code>{{ decision.filed_path }}</code><br>
      Source: <code>{{ decision.source_path }}</code><br>
      Confidence: {{ '%.2f' % decision.overall_confidence }}
      (person {{ '%.2f' % decision.person_confidence }},
       category {{ '%.2f' % decision.category_confidence }})
    </p>
  </div>
  <div class="actions">
    <h3>Classifier reasoning</h3>
    <p class="reasoning">{{ decision.reasoning or "(none)" }}</p>
    {% if decision.new_category_proposal %}
      <p class="proposal">Proposed new category: <code>{{ decision.new_category_proposal }}</code></p>
    {% endif %}

    <h3>Re-file</h3>
    <form id="refile-form" data-decision-id="{{ decision.id }}">
      <label>Person
        <select name="person_slug">
          {% for p in all_persons %}
            <option value="{{ p.slug }}" {% if p.slug == person_slug %}selected{% endif %}>
              {{ p.slug }} — {{ p.display_name }}
            </option>
          {% endfor %}
        </select>
      </label>
      <label>Category
        <select name="category_slug">
          {% for c in all_categories %}
            <option value="{{ c.slug }}" {% if c.slug == category_slug %}selected{% endif %}>
              {{ c.slug }} — {{ c.display_name }}
            </option>
          {% endfor %}
          {% if decision.new_category_proposal %}
            <option value="__new__:{{ decision.new_category_proposal }}">
              + create "{{ decision.new_category_proposal }}"
            </option>
          {% endif %}
        </select>
      </label>
      <label>Filename
        <input name="filename" value="{{ decision.proposed_filename }}">
      </label>
      <div class="buttons">
        <button type="button" id="btn-refile">Re-file</button>
        <button type="button" id="btn-approve">Approve as-is</button>
        <button type="button" id="btn-delete" class="danger">Delete</button>
      </div>
    </form>
  </div>
</div>
<script>
(function () {
  const form = document.getElementById("refile-form");
  const id = form.dataset.decisionId;
  function payload() {
    const fd = new FormData(form);
    return {
      person_slug: fd.get("person_slug"),
      category_slug: fd.get("category_slug"),
      filename: fd.get("filename"),
    };
  }
  document.getElementById("btn-refile").onclick = async () => {
    await aido.postJSON(`/decisions/${id}/re-file`, payload());
    location.reload();
  };
  document.getElementById("btn-approve").onclick = async () => {
    await aido.postJSON(`/decisions/${id}/approve`, {});
    location.reload();
  };
  document.getElementById("btn-delete").onclick = async () => {
    if (!confirm("Delete this document?")) return;
    await aido.postJSON(`/decisions/${id}/delete`, {});
    location.href = "/";
  };
})();
</script>
{% endblock %}
```

Add to `app.css`:
```css
.detail { display: grid; grid-template-columns: 1fr 1fr; gap: 1.25rem; }
.preview iframe { width: 100%; height: 70vh; border: 1px solid #374151;
                  background: #1f2937; }
.actions h3 { margin: 1rem 0 .25rem; }
.reasoning { background: #1f2937; padding: .6rem .8rem; border-radius: 6px; }
form#refile-form label { display: block; margin: .5rem 0; }
form#refile-form input, form#refile-form select {
  background: #111827; color: #e5e7eb; border: 1px solid #374151;
  border-radius: 4px; padding: .25rem .5rem; width: 100%;
}
.buttons { margin-top: 1rem; display: flex; gap: .5rem; }
.buttons button { padding: .4rem .9rem; border-radius: 5px;
                  border: 1px solid #374151; background: #1f2937;
                  color: #e5e7eb; cursor: pointer; }
.buttons button.danger { color: #fca5a5; border-color: #7f1d1d; }
```

- [ ] **Step 5: Implement `src/aido/webui/templates/stats.html`**

```html
{% extends "base.html" %}
{% block body %}
<h2>Stats</h2>
<dl class="stats">
  <dt>Total decisions</dt><dd>{{ total }}</dd>
  <dt>Last 7 days</dt><dd>{{ last7 }}</dd>
  <dt>Needs review</dt><dd>{{ needs_review_count }}</dd>
  <dt>Average auto-filed confidence</dt><dd>{{ '%.2f' % avg_confidence }}</dd>
</dl>
{% endblock %}
```

- [ ] **Step 6: Run tests, verify pass**

Run: `pytest tests/integration/test_webui_detail.py -v`
Expected: 5 passed.

- [ ] **Step 7: Commit**

```bash
git add src/aido/webui/
git commit -m "feat(webui): add detail page, PDF iframe stream, stats panel"
```

---

## Task 28: Mutation routes (POST /decisions/<id>/{re-file,approve,delete,rename,promote-category})

**Files:**
- Create: `src/aido/webui/mutation_routes.py`
- Modify: `src/aido/webui/app.py` to register the blueprint
- Test: `tests/integration/test_webui_mutations.py`

Thin glue: parse JSON, call `aido.mutations.*`, return `{"ok": true}`. Errors from mutations surface as 400/404/500 with a JSON body.

- [ ] **Step 1: Write failing test**

```python
# tests/integration/test_webui_mutations.py
import threading
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from aido.daemon import HealthState
from aido.mutations import MutationContext
from aido.store.connection import connect
from aido.store.decisions import (
    NewDecision,
    get_decision,
    insert_decision,
)
from aido.store.manual_actions import list_actions_for_decision
from aido.store.migrations import init_db
from aido.store.persons import create_person
from aido.store.taxonomy import create_category, create_doctype, get_category_by_slug
from aido.types import DecisionStatus, ManualAction
from aido.webui.app import WebState, create_app


@pytest.fixture
def web(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    db = tmp_path / "x.sqlite"
    with connect(db) as conn:
        init_db(conn)
        timo = create_person(conn, slug="timo", display_name="Timo")
        anna = create_person(conn, slug="anna", display_name="Anna")
        cat = create_category(conn, slug="rechnungen", display_name="Rechnungen")
        create_category(conn, slug="steuer", display_name="Steuer")
        create_category(conn, slug="_review", display_name="_review", is_review=True)
        dt = create_doctype(conn, slug="rechnung", display_name="Rechnung")
        filed = archive / "timo" / "rechnungen" / "x.pdf"
        filed.parent.mkdir(parents=True)
        filed.write_bytes(b"%PDF-1.4")
        new_id = insert_decision(conn, NewDecision(
            created_at=datetime(2026, 5, 17, 10, tzinfo=timezone.utc),
            source_hash="h1", source_path="/s/x.pdf", filed_path=str(filed),
            person_id=timo.id, category_id=cat.id, doctype_id=dt.id,
            document_date=date(2026, 3, 12), counterparty="telekom",
            proposed_filename="x.pdf",
            overall_confidence=0.93, person_confidence=0.95, category_confidence=0.91,
            reasoning="r", classifier_model="m",
            new_category_proposal=None, needs_review=False,
            status=DecisionStatus.AUTO_FILED,
        ))
    # Connection used by WebState — keep open for the duration of the test.
    state_conn_ctx = connect(db)
    conn = state_conn_ctx.__enter__()
    state = WebState(
        db_path=db,
        archive_root=archive,
        mutations=MutationContext(
            conn=conn,
            archive_root=archive,
            lock=threading.Lock(),
            now=lambda: datetime(2026, 5, 17, 12, tzinfo=timezone.utc),
        ),
        health=HealthState(),
    )
    app = create_app(state)
    app.config["TESTING"] = True
    yield app.test_client(), new_id
    state_conn_ctx.__exit__(None, None, None)


def test_post_refile_moves_and_audits(web):
    client, decision_id = web
    rv = client.post(f"/decisions/{decision_id}/re-file", json={
        "person_slug": "anna",
        "category_slug": "steuer",
        "filename": "moved.pdf",
    })
    assert rv.status_code == 200
    assert rv.get_json() == {"ok": True}
    state = client.application.config["AIDO_STATE"]
    d = get_decision(state.mutations.conn, decision_id)
    assert "anna" in d.filed_path and "steuer" in d.filed_path
    [audit] = list_actions_for_decision(state.mutations.conn, decision_id)
    assert audit.action == ManualAction.RE_FILE


def test_post_approve(web):
    client, decision_id = web
    state = client.application.config["AIDO_STATE"]
    state.mutations.conn.execute(
        "UPDATE decisions SET needs_review = 1 WHERE id = ?", (decision_id,)
    )
    rv = client.post(f"/decisions/{decision_id}/approve", json={})
    assert rv.status_code == 200
    d = get_decision(state.mutations.conn, decision_id)
    assert d.needs_review is False


def test_post_delete(web):
    client, decision_id = web
    rv = client.post(f"/decisions/{decision_id}/delete", json={})
    assert rv.status_code == 200


def test_post_promote_category_creates_and_refiles(web):
    client, decision_id = web
    state = client.application.config["AIDO_STATE"]
    rv = client.post(f"/decisions/{decision_id}/promote-category", json={
        "new_category_slug": "garten",
        "new_category_display_name": "Garten",
        "person_slug": "timo",
        "filename": "garten_doc.pdf",
    })
    assert rv.status_code == 200
    assert get_category_by_slug(state.mutations.conn, "garten") is not None


def test_unknown_decision_returns_404(web):
    client, _ = web
    rv = client.post("/decisions/9999/re-file", json={
        "person_slug": "anna", "category_slug": "steuer", "filename": "x.pdf",
    })
    assert rv.status_code == 404
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/integration/test_webui_mutations.py -v`
Expected: 404s on the new endpoints.

- [ ] **Step 3: Implement `src/aido/webui/mutation_routes.py`**

```python
"""POST endpoints that call into aido.mutations under the daemon's lock."""
from __future__ import annotations

from flask import Blueprint, abort, current_app, jsonify, request

from aido.mutations import (
    MutationContext,
    approve,
    delete_decision,
    promote_category,
    re_file,
    rename,
)
from aido.store.persons import get_person_by_slug
from aido.store.taxonomy import get_category_by_slug

bp = Blueprint("mutations", __name__)


def _ctx() -> MutationContext:
    return current_app.config["AIDO_STATE"].mutations


def _resolve_person_id(slug: str) -> int:
    person = get_person_by_slug(_ctx().conn, slug)
    if person is None:
        abort(400, description=f"Unknown person slug: {slug}")
    return person.id


def _resolve_category_id(slug: str) -> int:
    cat = get_category_by_slug(_ctx().conn, slug)
    if cat is None:
        abort(400, description=f"Unknown category slug: {slug}")
    return cat.id


@bp.post("/decisions/<int:decision_id>/re-file")
def post_refile(decision_id: int):
    body = request.get_json(force=True) or {}
    try:
        re_file(
            _ctx(),
            decision_id,
            person_id=_resolve_person_id(body["person_slug"]),
            category_id=_resolve_category_id(body["category_slug"]),
            filename=body["filename"],
            note=body.get("note"),
        )
    except ValueError as e:
        if "Unknown decision" in str(e):
            abort(404)
        abort(400, description=str(e))
    return jsonify({"ok": True})


@bp.post("/decisions/<int:decision_id>/rename")
def post_rename(decision_id: int):
    body = request.get_json(force=True) or {}
    try:
        rename(_ctx(), decision_id, filename=body["filename"], note=body.get("note"))
    except ValueError as e:
        if "Unknown decision" in str(e):
            abort(404)
        abort(400, description=str(e))
    return jsonify({"ok": True})


@bp.post("/decisions/<int:decision_id>/delete")
def post_delete(decision_id: int):
    body = request.get_json(silent=True) or {}
    try:
        delete_decision(_ctx(), decision_id, note=body.get("note"))
    except ValueError as e:
        if "Unknown decision" in str(e):
            abort(404)
        abort(400, description=str(e))
    return jsonify({"ok": True})


@bp.post("/decisions/<int:decision_id>/approve")
def post_approve(decision_id: int):
    body = request.get_json(silent=True) or {}
    try:
        approve(_ctx(), decision_id, note=body.get("note"))
    except ValueError as e:
        if "Unknown decision" in str(e):
            abort(404)
        abort(400, description=str(e))
    return jsonify({"ok": True})


@bp.post("/decisions/<int:decision_id>/promote-category")
def post_promote(decision_id: int):
    body = request.get_json(force=True) or {}
    try:
        promote_category(
            _ctx(),
            decision_id,
            new_category_slug=body["new_category_slug"],
            new_category_display_name=body["new_category_display_name"],
            person_id=_resolve_person_id(body["person_slug"]),
            filename=body["filename"],
            note=body.get("note"),
        )
    except ValueError as e:
        if "Unknown decision" in str(e):
            abort(404)
        abort(400, description=str(e))
    return jsonify({"ok": True})
```

- [ ] **Step 4: Register the blueprint**

In `src/aido/webui/app.py`, inside `create_app()` after the feed blueprint registration:

```python
    from aido.webui.mutation_routes import bp as mut_bp
    app.register_blueprint(mut_bp)
```

- [ ] **Step 5: Run tests, verify pass**

Run: `pytest tests/integration/test_webui_mutations.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add src/aido/webui/mutation_routes.py src/aido/webui/app.py tests/integration/test_webui_mutations.py
git commit -m "feat(webui): add POST mutation routes wired to mutations module"
```

---

## Task 29: Settings page (persons / categories / doctypes / aliases admin)

**Files:**
- Create: `src/aido/webui/settings_routes.py`
- Create: `src/aido/webui/templates/settings.html`
- Modify: `src/aido/webui/app.py` to register the blueprint
- Test: `tests/integration/test_webui_settings.py`

Lists all persons + their aliases, categories, doctypes. Provides POST forms to add a person, add an alias, add a category, add a doctype. Read-only delete: deactivate (set `is_active = 0`).

- [ ] **Step 1: Write failing test**

```python
# tests/integration/test_webui_settings.py
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from aido.daemon import HealthState
from aido.mutations import MutationContext
from aido.store.connection import connect
from aido.store.migrations import init_db
from aido.store.persons import create_person, find_person_by_alias, list_aliases_for, get_person_by_slug
from aido.store.taxonomy import create_category, get_category_by_slug, get_doctype_by_slug
from aido.webui.app import WebState, create_app


@pytest.fixture
def web(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    db = tmp_path / "x.sqlite"
    with connect(db) as conn:
        init_db(conn)
        create_person(conn, slug="timo", display_name="Timo")
        create_category(conn, slug="_review", display_name="_review", is_review=True)
    state_conn_ctx = connect(db)
    conn = state_conn_ctx.__enter__()
    state = WebState(
        db_path=db, archive_root=archive,
        mutations=MutationContext(
            conn=conn, archive_root=archive, lock=threading.Lock(),
            now=lambda: datetime.now(timezone.utc),
        ),
        health=HealthState(),
    )
    app = create_app(state)
    app.config["TESTING"] = True
    yield app.test_client(), conn
    state_conn_ctx.__exit__(None, None, None)


def test_settings_renders(web):
    client, _ = web
    rv = client.get("/settings")
    assert rv.status_code == 200
    body = rv.get_data(as_text=True)
    assert "timo" in body
    assert "Persons" in body
    assert "Categories" in body
    assert "Doctypes" in body


def test_add_person(web):
    client, conn = web
    rv = client.post("/settings/persons", json={
        "slug": "anna", "display_name": "Anna Jakob", "is_shared": False,
        "aliases": ["Anna Jakob"],
    })
    assert rv.status_code == 200
    assert get_person_by_slug(conn, "anna") is not None
    p = get_person_by_slug(conn, "anna")
    assert [a.alias for a in list_aliases_for(conn, p.id)] == ["Anna Jakob"]


def test_add_alias_to_existing(web):
    client, conn = web
    timo = get_person_by_slug(conn, "timo")
    rv = client.post(f"/settings/persons/{timo.id}/aliases", json={"alias": "Jakob"})
    assert rv.status_code == 200
    assert find_person_by_alias(conn, "jakob").id == timo.id


def test_add_category(web):
    client, conn = web
    rv = client.post("/settings/categories", json={
        "slug": "garten", "display_name": "Garten", "description": "Garten-Sachen",
    })
    assert rv.status_code == 200
    assert get_category_by_slug(conn, "garten") is not None


def test_add_doctype(web):
    client, conn = web
    rv = client.post("/settings/doctypes", json={
        "slug": "gartenrechnung", "display_name": "Gartenrechnung",
    })
    assert rv.status_code == 200
    assert get_doctype_by_slug(conn, "gartenrechnung") is not None


def test_duplicate_slug_returns_400(web):
    client, _ = web
    client.post("/settings/categories", json={"slug": "garten", "display_name": "G"})
    rv = client.post("/settings/categories", json={"slug": "garten", "display_name": "G2"})
    assert rv.status_code == 400
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/integration/test_webui_settings.py -v`
Expected: 404s.

- [ ] **Step 3: Implement `src/aido/webui/settings_routes.py`**

```python
"""Settings page: list and admin persons/aliases/categories/doctypes."""
from __future__ import annotations

import sqlite3

from flask import Blueprint, abort, current_app, jsonify, render_template, request

from aido.store.connection import connect
from aido.store.decisions import count_needs_review
from aido.store.persons import (
    add_alias,
    create_person,
    get_person_by_slug,
    list_aliases_for,
    list_persons,
)
from aido.store.taxonomy import (
    create_category,
    create_doctype,
    get_category_by_slug,
    get_doctype_by_slug,
    list_categories,
    list_doctypes,
)

bp = Blueprint("settings", __name__)


def _state():
    return current_app.config["AIDO_STATE"]


@bp.route("/settings")
def settings_page() -> str:
    state = _state()
    with connect(state.db_path) as conn:
        persons = list_persons(conn, include_inactive=True)
        aliases_by_person = {p.id: list_aliases_for(conn, p.id) for p in persons}
        cats = list_categories(conn, include_inactive=True)
        doctypes = list_doctypes(conn, include_inactive=True)
        pending = count_needs_review(conn)
    return render_template(
        "settings.html",
        persons=persons,
        aliases_by_person=aliases_by_person,
        categories=cats,
        doctypes=doctypes,
        needs_review_count=pending,
        health=state.health.status.value,
    )


def _conn() -> sqlite3.Connection:
    return _state().mutations.conn


@bp.post("/settings/persons")
def add_person_route():
    body = request.get_json(force=True) or {}
    slug = body["slug"]
    if get_person_by_slug(_conn(), slug) is not None:
        abort(400, description=f"Person slug {slug!r} already exists")
    with _conn():
        person = create_person(
            _conn(),
            slug=slug,
            display_name=body["display_name"],
            is_shared=bool(body.get("is_shared", False)),
        )
        for alias in body.get("aliases") or []:
            add_alias(_conn(), person_id=person.id, alias=alias)
    return jsonify({"ok": True, "id": person.id})


@bp.post("/settings/persons/<int:person_id>/aliases")
def add_alias_route(person_id: int):
    body = request.get_json(force=True) or {}
    try:
        with _conn():
            row = add_alias(_conn(), person_id=person_id, alias=body["alias"])
    except sqlite3.IntegrityError as e:
        abort(400, description=str(e))
    return jsonify({"ok": True, "id": row.id})


@bp.post("/settings/categories")
def add_category_route():
    body = request.get_json(force=True) or {}
    slug = body["slug"]
    if get_category_by_slug(_conn(), slug) is not None:
        abort(400, description=f"Category slug {slug!r} already exists")
    with _conn():
        cat = create_category(
            _conn(),
            slug=slug,
            display_name=body["display_name"],
            description=body.get("description"),
        )
    return jsonify({"ok": True, "id": cat.id})


@bp.post("/settings/doctypes")
def add_doctype_route():
    body = request.get_json(force=True) or {}
    slug = body["slug"]
    if get_doctype_by_slug(_conn(), slug) is not None:
        abort(400, description=f"Doctype slug {slug!r} already exists")
    with _conn():
        dt = create_doctype(
            _conn(),
            slug=slug,
            display_name=body["display_name"],
            description=body.get("description"),
        )
    return jsonify({"ok": True, "id": dt.id})
```

- [ ] **Step 4: Implement `src/aido/webui/templates/settings.html`**

```html
{% extends "base.html" %}
{% block body %}
<h2>Settings</h2>

<section>
  <h3>Persons</h3>
  <table>
    <tr><th>Slug</th><th>Display</th><th>Shared?</th><th>Aliases</th></tr>
    {% for p in persons %}
      <tr>
        <td>{{ p.slug }}</td>
        <td>{{ p.display_name }}</td>
        <td>{{ "yes" if p.is_shared else "no" }}</td>
        <td>{{ aliases_by_person[p.id] | map(attribute='alias') | join(', ') }}</td>
      </tr>
    {% endfor %}
  </table>
  <details>
    <summary>Add person</summary>
    <form id="add-person">
      <label>Slug <input name="slug"></label>
      <label>Display name <input name="display_name"></label>
      <label>Aliases (comma-separated) <input name="aliases"></label>
      <label><input type="checkbox" name="is_shared"> shared bucket</label>
      <button type="button" id="add-person-btn">Add</button>
    </form>
  </details>
</section>

<section>
  <h3>Categories</h3>
  <table>
    <tr><th>Slug</th><th>Display</th><th>Description</th><th>Review?</th></tr>
    {% for c in categories %}
      <tr>
        <td>{{ c.slug }}</td><td>{{ c.display_name }}</td>
        <td>{{ c.description or "" }}</td>
        <td>{{ "yes" if c.is_review else "" }}</td>
      </tr>
    {% endfor %}
  </table>
  <details>
    <summary>Add category</summary>
    <form id="add-category">
      <label>Slug <input name="slug"></label>
      <label>Display <input name="display_name"></label>
      <label>Description <input name="description"></label>
      <button type="button" id="add-category-btn">Add</button>
    </form>
  </details>
</section>

<section>
  <h3>Doctypes</h3>
  <table>
    <tr><th>Slug</th><th>Display</th><th>Description</th></tr>
    {% for d in doctypes %}
      <tr><td>{{ d.slug }}</td><td>{{ d.display_name }}</td><td>{{ d.description or "" }}</td></tr>
    {% endfor %}
  </table>
  <details>
    <summary>Add doctype</summary>
    <form id="add-doctype">
      <label>Slug <input name="slug"></label>
      <label>Display <input name="display_name"></label>
      <label>Description <input name="description"></label>
      <button type="button" id="add-doctype-btn">Add</button>
    </form>
  </details>
</section>

<script>
(function () {
  function values(form) {
    const fd = new FormData(form);
    const out = {};
    for (const [k, v] of fd.entries()) out[k] = v;
    if ("aliases" in out) out.aliases = out.aliases.split(",").map(s => s.trim()).filter(Boolean);
    if ("is_shared" in out) out.is_shared = true; else out.is_shared = false;
    return out;
  }
  document.getElementById("add-person-btn").onclick = async () => {
    await aido.postJSON("/settings/persons", values(document.getElementById("add-person")));
    location.reload();
  };
  document.getElementById("add-category-btn").onclick = async () => {
    await aido.postJSON("/settings/categories", values(document.getElementById("add-category")));
    location.reload();
  };
  document.getElementById("add-doctype-btn").onclick = async () => {
    await aido.postJSON("/settings/doctypes", values(document.getElementById("add-doctype")));
    location.reload();
  };
})();
</script>
{% endblock %}
```

- [ ] **Step 5: Register the blueprint**

In `src/aido/webui/app.py` inside `create_app()`:

```python
    from aido.webui.settings_routes import bp as settings_bp
    app.register_blueprint(settings_bp)
```

- [ ] **Step 6: Run tests, verify pass**

Run: `pytest tests/integration/test_webui_settings.py -v`
Expected: 6 passed.

- [ ] **Step 7: Commit**

```bash
git add src/aido/webui/
git commit -m "feat(webui): add /settings page + POST routes for taxonomy admin"
```

---

## Task 30: Main entrypoint — daemon + web UI together

**Files:**
- Create: `src/aido/main.py`
- Modify: `src/aido/__main__.py` to dispatch `run` to `aido.main:run`
- Test: `tests/integration/test_main_entrypoint.py`

`python -m aido run` loads config, opens the DB, builds classifier + daemon + web app, installs SIGTERM handler, and runs Flask in the main thread while the daemon worker runs in a background thread.

- [ ] **Step 1: Write failing test**

```python
# tests/integration/test_main_entrypoint.py
import threading
import time
from pathlib import Path

import pytest

from aido.main import RuntimeContext, build_runtime


def _write_config(path: Path, *, archive, inbox, db, log) -> Path:
    path.write_text(f"""
archive_root: {archive}
scan_inbox: {inbox}
db_path: {db}
log_path: {log}

classifier:
  backend: fake
  model: claude-opus-4-7
  review_confidence_threshold: 0.75

web:
  bind: 127.0.0.1
  port: 0
""".strip(), encoding="utf-8")
    return path


def test_build_runtime_returns_wired_context(tmp_path: Path):
    archive = tmp_path / "archive"
    inbox = tmp_path / "inbox"
    archive.mkdir(); inbox.mkdir()
    cfg = _write_config(
        tmp_path / "config.yaml",
        archive=archive, inbox=inbox,
        db=tmp_path / "aido.sqlite", log=tmp_path / "aido.log",
    )

    rt = build_runtime(config_path=cfg, pidfile=tmp_path / "aido.pid")
    assert isinstance(rt, RuntimeContext)
    assert rt.daemon is not None
    assert rt.app is not None
    # Don't actually run Flask in the test; just confirm the app has our routes.
    routes = {r.rule for r in rt.app.url_map.iter_rules()}
    assert "/" in routes
    assert "/healthz" in routes
    assert "/settings" in routes
    # Clean up the daemon's DB context so the temp dir can be removed.
    rt.shutdown()


def test_main_entrypoint_starts_and_stops(tmp_path: Path):
    """Sanity: invoking aido.main.run() in a thread and signalling stop
    should exit cleanly without leaving the pidfile behind.
    """
    archive = tmp_path / "archive"
    inbox = tmp_path / "inbox"
    archive.mkdir(); inbox.mkdir()
    cfg = _write_config(
        tmp_path / "config.yaml",
        archive=archive, inbox=inbox,
        db=tmp_path / "aido.sqlite", log=tmp_path / "aido.log",
    )
    pidfile = tmp_path / "aido.pid"

    from aido.main import run

    started = threading.Event()
    stopped = threading.Event()
    rt_holder: dict = {}

    def runner():
        rt_holder["rt"] = run(
            config_path=cfg, pidfile=pidfile,
            ready_event=started, stop_event=stopped, run_web=False,
        )

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    assert started.wait(timeout=5)
    assert pidfile.exists()
    stopped.set()
    t.join(timeout=10)
    assert not t.is_alive()
    assert not pidfile.exists()
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/integration/test_main_entrypoint.py -v`
Expected: module missing.

- [ ] **Step 3: Implement `src/aido/main.py`**

```python
"""Main entrypoint: wires config → daemon → web UI and runs them together."""
from __future__ import annotations

import argparse
import logging
import signal
import sqlite3
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from aido.classifier.factory import build_classifier
from aido.config import Config, load_config
from aido.daemon import Daemon
from aido.logging_setup import configure_logging
from aido.webui.app import WebState, create_app

_log = logging.getLogger("aido.main")


@dataclass
class RuntimeContext:
    config: Config
    daemon: Daemon
    app: object  # Flask
    state: WebState
    _conn: sqlite3.Connection
    _conn_ctx: object

    def shutdown(self) -> None:
        self.daemon.stop()


def build_runtime(*, config_path: Path, pidfile: Path) -> RuntimeContext:
    cfg = load_config(config_path)
    configure_logging(cfg.log_path)

    daemon = Daemon(
        db_path=cfg.db_path,
        archive_root=cfg.archive_root,
        inbox=cfg.scan_inbox,
        classifier_factory=lambda conn: build_classifier(conn, cfg.classifier),
        threshold=cfg.classifier.review_confidence_threshold,
        classifier_model=cfg.classifier.model,
        pidfile=pidfile,
    )
    daemon.start()

    # WebState shares the daemon's connection + mutation context so both the
    # worker thread and HTTP handlers serialize through the same lock.
    state = WebState(
        db_path=cfg.db_path,
        archive_root=cfg.archive_root,
        mutations=daemon._mutations,  # type: ignore[attr-defined]
        health=daemon.health,
    )
    app = create_app(state)
    return RuntimeContext(
        config=cfg,
        daemon=daemon,
        app=app,
        state=state,
        _conn=daemon._conn,  # type: ignore[attr-defined]
        _conn_ctx=daemon._connection_ctx,  # type: ignore[attr-defined]
    )


def run(
    *,
    config_path: Path,
    pidfile: Path,
    ready_event: threading.Event | None = None,
    stop_event: threading.Event | None = None,
    run_web: bool = True,
) -> RuntimeContext:
    """Build the runtime, run web UI in main thread, return after shutdown.

    `ready_event` / `stop_event` are used by tests to coordinate startup +
    shutdown without actually starting Flask. `run_web=False` skips Flask
    entirely (the daemon worker still runs).
    """
    rt = build_runtime(config_path=config_path, pidfile=pidfile)

    if ready_event is not None:
        ready_event.set()

    if run_web:
        def _sigterm(*_):
            rt.shutdown()
            sys.exit(0)
        signal.signal(signal.SIGTERM, _sigterm)
        signal.signal(signal.SIGINT, _sigterm)
        try:
            rt.app.run(  # type: ignore[attr-defined]
                host=rt.config.web.bind,
                port=rt.config.web.port,
                threaded=True,
                use_reloader=False,
            )
        finally:
            rt.shutdown()
    elif stop_event is not None:
        stop_event.wait()
        rt.shutdown()
    return rt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aido-daemon")
    parser.add_argument("--config", type=Path, default=Path("/app/config.yaml"))
    parser.add_argument("--pidfile", type=Path, default=Path("/var/run/aido.pid"))
    args = parser.parse_args(argv)
    run(config_path=args.config, pidfile=args.pidfile)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Update `src/aido/__main__.py`**

Replace the contents of `src/aido/__main__.py` with:

```python
"""`python -m aido` dispatches to either the CLI or the daemon entrypoint.

  python -m aido init ...           → CLI (Task 24)
  python -m aido status ...         → CLI
  python -m aido rebuild-index ...  → CLI
  python -m aido run [--config ...] → daemon + web (this task)
"""
from __future__ import annotations

import sys


def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] == "run":
        from aido.main import main as daemon_main
        return daemon_main(argv[1:])
    from aido.cli import main as cli_main
    return cli_main(argv)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run tests, verify pass**

Run: `pytest tests/integration/test_main_entrypoint.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add src/aido/main.py src/aido/__main__.py tests/integration/test_main_entrypoint.py
git commit -m "feat(main): add combined daemon+webui entrypoint (python -m aido run)"
```

---

## Task 31: Dockerfile + docker-compose.yml + .dockerignore

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.dockerignore`
- Test: `tests/integration/test_dockerfile.py` (smoke: image builds, container starts and responds to /healthz)

This task is the only one requiring Docker on the host machine. The test is skipped if `docker` is unavailable.

- [ ] **Step 1: Write `Dockerfile`**

```dockerfile
FROM python:3.13-slim AS base

# Node.js is needed because the Claude Agent SDK spawns the bundled Claude
# Code CLI as a subprocess.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        nodejs \
        npm \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged runtime user (matches macOS UID 501 by default).
ARG UID=501
ARG GID=20
RUN groupadd -g ${GID} aido \
    && useradd -m -u ${UID} -g ${GID} -s /bin/bash aido

WORKDIR /app

# Copy install metadata first so the dependency layer caches between rebuilds.
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# Source last so code edits don't bust the deps layer.
COPY src/ ./src/

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8765
USER aido

CMD ["python", "-m", "aido", "run", "--config", "/app/config.yaml", "--pidfile", "/tmp/aido.pid"]
```

- [ ] **Step 2: Write `docker-compose.yml`**

```yaml
services:
  aido:
    build:
      context: .
      args:
        UID: ${AIDO_UID:-501}
        GID: ${AIDO_GID:-20}
    image: aido:latest
    container_name: aido
    restart: unless-stopped
    ports:
      - "127.0.0.1:8765:8765"
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - ./data:/data
      - ./logs:/var/log/aido
      - "${HOME}/Scans/incoming:/scans:rw"
      - "${HOME}/Documents/Archive:/archive:rw"
      - "${HOME}/.claude:/home/aido/.claude:rw"
    environment:
      - CLAUDE_CONFIG_DIR=/home/aido/.claude
      - TZ=Europe/Berlin
```

- [ ] **Step 3: Write `.dockerignore`**

```
.git
.venv/
__pycache__/
*.pyc
*.pyo
.pytest_cache/
docs/
tests/
.superpowers/
data/
logs/
*.sqlite
*.sqlite-*
```

- [ ] **Step 4: Write smoke test `tests/integration/test_dockerfile.py`**

```python
"""Smoke test: build the image and curl /healthz inside the container."""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

DOCKER_AVAILABLE = shutil.which("docker") is not None
REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(not DOCKER_AVAILABLE, reason="docker not on PATH")
def test_image_builds_and_healthz_responds(tmp_path: Path):
    # Build image with a unique tag so we don't trample local state.
    tag = f"aido-test:{os.getpid()}"
    subprocess.run(
        ["docker", "build", "-t", tag, "."],
        cwd=REPO_ROOT, check=True,
    )

    # Prepare minimal mounts.
    data = tmp_path / "data"; data.mkdir()
    logs = tmp_path / "logs"; logs.mkdir()
    archive = tmp_path / "archive"; archive.mkdir()
    inbox = tmp_path / "inbox"; inbox.mkdir()
    cfg = tmp_path / "config.yaml"
    cfg.write_text(f"""
archive_root: /archive
scan_inbox: /scans
db_path: /data/aido.sqlite
log_path: /var/log/aido/aido.log

classifier:
  backend: fake
  model: claude-opus-4-7
  review_confidence_threshold: 0.75

web:
  bind: 0.0.0.0
  port: 8765
""".strip(), encoding="utf-8")

    # Seed an _review category etc. by running aido init inside the container.
    seed = tmp_path / "seed.yaml"
    seed.write_text("""
persons:
  - slug: timo
    display_name: Timo
    aliases: [Timo]
  - slug: shared
    display_name: Shared
    is_shared: true
    aliases: []
categories:
  - slug: rechnungen
    display_name: Rechnungen
doctypes:
  - slug: rechnung
    display_name: Rechnung
""".strip(), encoding="utf-8")

    init_args = [
        "docker", "run", "--rm",
        "-v", f"{cfg}:/app/config.yaml:ro",
        "-v", f"{data}:/data",
        "-v", f"{logs}:/var/log/aido",
        "-v", f"{archive}:/archive",
        "-v", f"{inbox}:/scans",
        "-v", f"{seed}:/tmp/seed.yaml:ro",
        tag,
        "python", "-m", "aido", "init",
        "--db", "/data/aido.sqlite", "--seed", "/tmp/seed.yaml",
    ]
    subprocess.run(init_args, check=True)

    # Launch container in background and curl /healthz on the mapped port.
    port = 18765
    name = f"aido-test-{os.getpid()}"
    run_args = [
        "docker", "run", "-d", "--name", name,
        "-p", f"127.0.0.1:{port}:8765",
        "-v", f"{cfg}:/app/config.yaml:ro",
        "-v", f"{data}:/data",
        "-v", f"{logs}:/var/log/aido",
        "-v", f"{archive}:/archive",
        "-v", f"{inbox}:/scans",
        tag,
    ]
    subprocess.run(run_args, check=True)
    try:
        ok = False
        for _ in range(30):
            time.sleep(1)
            r = subprocess.run(
                ["curl", "-fsS", f"http://127.0.0.1:{port}/healthz"],
                capture_output=True,
            )
            if r.returncode == 0 and b'"status"' in r.stdout:
                ok = True
                break
        assert ok, "container never responded on /healthz"
    finally:
        subprocess.run(["docker", "rm", "-f", name], check=False)
        subprocess.run(["docker", "image", "rm", tag], check=False)
```

- [ ] **Step 5: Run the smoke test (if Docker is installed)**

Run: `pytest tests/integration/test_dockerfile.py -v`
Expected: 1 passed (or 1 skipped if Docker is not available on the dev machine).

- [ ] **Step 6: Commit**

```bash
git add Dockerfile docker-compose.yml .dockerignore tests/integration/test_dockerfile.py
git commit -m "feat(docker): add Dockerfile, docker-compose.yml, smoke test"
```

---

## Task 32: End-to-end test (PDF dropped → filed → re-filed via web)

**Files:**
- Create: `tests/integration/test_e2e.py`

One test exercises the whole stack against the in-process Flask test client and `FakeClassifier`: drop a PDF in the inbox, wait until the daemon files it, then POST `/decisions/<id>/re-file` and confirm the file moved.

- [ ] **Step 1: Write failing test**

```python
# tests/integration/test_e2e.py
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from aido.classifier.fake import FakeClassifier
from aido.daemon import Daemon
from aido.mutations import MutationContext
from aido.store.connection import connect
from aido.store.decisions import find_by_source_hash, list_recent
from aido.store.migrations import init_db
from aido.store.persons import create_person
from aido.store.taxonomy import create_category, create_doctype
from aido.types import ClassificationResult
from aido.webui.app import WebState, create_app
from aido.pdf.hash import sha256_of_file
from tests.fixtures import synth_pdf


def _result(person="timo", cat="rechnungen", filename="2026-03-12_rechnung_telekom.pdf"):
    return ClassificationResult(
        person_slug=person,
        category_slug=cat,
        doctype_slug="rechnung",
        document_date=date(2026, 3, 12),
        counterparty="telekom",
        proposed_filename=filename,
        overall_confidence=0.93,
        person_confidence=0.95,
        category_confidence=0.91,
        new_category_proposal=None,
        reasoning="recipient Timo; sender Telekom",
    )


def test_e2e_drop_file_audit_refile(tmp_path: Path):
    archive = tmp_path / "archive"; archive.mkdir()
    inbox = tmp_path / "inbox"; inbox.mkdir()
    db = tmp_path / "x.sqlite"
    with connect(db) as conn:
        init_db(conn)
        create_person(conn, slug="timo", display_name="Timo")
        create_person(conn, slug="anna", display_name="Anna")
        create_person(conn, slug="shared", display_name="Shared", is_shared=True)
        create_category(conn, slug="rechnungen", display_name="Rechnungen")
        create_category(conn, slug="steuer", display_name="Steuer")
        create_category(conn, slug="_review", display_name="_review", is_review=True)
        create_doctype(conn, slug="rechnung", display_name="Rechnung")
        create_doctype(conn, slug="letter", display_name="Letter")

    fake = FakeClassifier(results=[_result()])

    daemon = Daemon(
        db_path=db,
        archive_root=archive,
        inbox=inbox,
        classifier_factory=lambda conn: fake,
        threshold=0.75,
        classifier_model="claude-opus-4-7",
        pidfile=tmp_path / "aido.pid",
        poll_interval=0.2,
        stabilize_seconds=0.0,
    )
    daemon.start()
    try:
        pdf = synth_pdf(inbox / "scan001.pdf", text=["Telekom Rechnung", "Timo Jakob"])
        # Wait for the daemon to file it (expected within ~3s).
        decision_id = None
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with connect(db) as conn:
                rows = list_recent(conn, limit=1)
                if rows:
                    decision_id = rows[0].id
                    break
            time.sleep(0.2)
        assert decision_id is not None, "daemon never filed the dropped PDF"

        # Run the web UI against the daemon's mutation context.
        state = WebState(
            db_path=db,
            archive_root=archive,
            mutations=daemon._mutations,  # type: ignore[attr-defined]
            health=daemon.health,
        )
        app = create_app(state)
        client = app.test_client()

        # Confirm the detail page renders.
        rv = client.get(f"/decisions/{decision_id}")
        assert rv.status_code == 200

        # Re-file under anna/steuer.
        rv = client.post(f"/decisions/{decision_id}/re-file", json={
            "person_slug": "anna",
            "category_slug": "steuer",
            "filename": "2026-03-12_rechnung_telekom.pdf",
        })
        assert rv.status_code == 200, rv.data

        # Verify the file actually moved.
        moved = archive / "anna" / "steuer" / "2026-03-12_rechnung_telekom.pdf"
        assert moved.exists()
    finally:
        daemon.stop()
```

- [ ] **Step 2: Run test, verify it works**

Run: `pytest tests/integration/test_e2e.py -v`
Expected: 1 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_e2e.py
git commit -m "test(e2e): drop a PDF, observe filing, re-file via web UI"
```

---

## Task 33: Manual smoke runbook

**Files:**
- Create: `tests/manual/runbook.md`

A short checklist for the human operator to confirm the system behaves correctly on the real host with real Claude calls. Not run by pytest.

- [ ] **Step 1: Write `tests/manual/runbook.md`**

```markdown
# aido manual smoke runbook

Run this checklist after a fresh deployment on the MacBook Pro (and again on
the Mac mini after migration). It exercises paths automated tests cannot
cover: the real Claude Agent SDK, real PDFs from the scanner, the LAN web UI.

## Pre-flight

- [ ] `claude login` has been run on the host; `~/.claude/.credentials.json`
      exists and is non-empty.
- [ ] `~/Scans/incoming/` and `~/Documents/Archive/` exist and are writable
      by the user that owns the Docker volumes.
- [ ] `docker compose ps` shows no stale `aido` container.

## First-run bootstrap

- [ ] `docker compose build` succeeds.
- [ ] `docker compose run --rm aido python -m aido init --db /data/aido.sqlite \
       --archive-root /archive --scan-inbox /scans` walks through the four
      family members + shared bucket without errors.
- [ ] `data/aido.sqlite` exists on the host.
- [ ] `docker compose up -d` starts the container; `docker compose logs -f`
      shows `aido.daemon` starting up cleanly and `Running on http://0.0.0.0:8765`.
- [ ] `curl http://localhost:8765/healthz` returns `{"status":"ok",...}`.

## Smoke documents

Drop the following into `~/Scans/incoming/` (one at a time, waiting for each
to be filed before adding the next):

- [ ] **DE invoice** addressed to one named family member. Expected: filed
      under `<person>/rechnungen/YYYY-MM-DD_rechnung_<vendor>.pdf` with
      confidence ≥ 0.8.
- [ ] **EN invoice** addressed to the same family member. Expected: filed
      similarly; English text should not impact confidence noticeably.
- [ ] **Multi-addressee letter** (e.g., utility bill addressed to two
      spouses). Expected: filed under the first-named person, NOT shared.
- [ ] **Household-only letter** addressed to "Familie Jakob" with no
      individual name. Expected: filed under `shared/`.
- [ ] **Image-only PDF** (a photo-scan with no text layer). Expected: filed
      under `_review/` with reason `no_extractable_text`.

## Web UI sanity

- [ ] Open `http://localhost:8765` in a desktop browser. Recently filed list
      shows the smoke documents above, most recent first.
- [ ] `Needs review` tab shows only the image-only PDF.
- [ ] Click the image-only PDF → detail page renders, iframe shows the PDF.
- [ ] Re-file the image-only PDF as `letters` under `shared`. Page reloads;
      the file is now under `shared/letters/` on disk.
- [ ] Open `http://<host>.local:8765` from a phone or tablet on the same LAN.
      (Requires editing `docker-compose.yml` to bind `0.0.0.0` instead of
      `127.0.0.1`.)

## Lifecycle

- [ ] `docker compose restart aido` brings the container back without
      losing data. The recently-filed list is still populated; the web UI
      still responds.
- [ ] Drop another PDF after the restart; it gets filed normally.
- [ ] `docker compose down` stops the container cleanly (no pidfile left on
      the host's mounted `data/` volume).
```

- [ ] **Step 2: Commit**

```bash
git add tests/manual/runbook.md
git commit -m "docs: add manual smoke runbook for first-run + post-restart"
```

---

## Task 34: README (first-run quickstart)

**Files:**
- Create: `README.md`

Minimal: what it is, how to bootstrap and run on macOS, where the spec and plan live.

- [ ] **Step 1: Write `README.md`**

```markdown
# aido — household document organizer

`aido` watches a scanner inbox folder, classifies each incoming PDF with
Claude, and files it into `<archive>/<person>/<category>/YYYY-MM-DD_<doctype>_<counterparty>.pdf`.
A small Flask web UI lets you audit and correct decisions retrospectively.

For a 4-person household sharing one scanner. Runs on macOS (Apple Silicon)
via Docker Compose.

## Spec & implementation plan

- Design: [`docs/superpowers/specs/2026-05-17-ai-doc-organizer-design.md`](docs/superpowers/specs/2026-05-17-ai-doc-organizer-design.md)
- Implementation plan: [`docs/superpowers/plans/2026-05-17-ai-doc-organizer-v1.md`](docs/superpowers/plans/2026-05-17-ai-doc-organizer-v1.md)

## First-run (macOS host)

1. Install the Claude Code CLI and authenticate to your Max Plan:
   ```bash
   curl -fsSL https://claude.ai/install.sh | bash
   claude login
   ```
2. Clone this repo and `cd` into it. Copy the example config:
   ```bash
   cp config.example.yaml config.yaml
   ```
3. Build the image and bootstrap the database:
   ```bash
   docker compose build
   docker compose run --rm aido python -m aido init \
       --db /data/aido.sqlite \
       --archive-root /archive --scan-inbox /scans
   ```
4. Start the daemon:
   ```bash
   docker compose up -d
   ```
5. Open `http://localhost:8765`. Drop a PDF into `~/Scans/incoming/` and
   watch it get filed.

See `tests/manual/runbook.md` for the full smoke checklist.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -v
```

Tests are network-free by default; the `claude-agent-sdk` interaction is
mocked. The Docker smoke test in `tests/integration/test_dockerfile.py` is
skipped automatically if `docker` is not on `PATH`.

## License

(Not yet decided — keep private until decided.)
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with first-run quickstart"
```

---

## Known v1 scope deferrals

These are deliberate simplifications relative to the spec; revisit during the
post-MVP feedback iteration.

- **`pending_jobs` retry loop**: the table exists (Task 10) and the schema
  matches the spec, but the worker pipeline routes every classifier failure
  directly to `_review/` instead of scheduling a retry with exponential
  backoff (spec §9). Acceptable because `_review/` is a safe-by-default
  parking spot — nothing is silently lost. Wire the retry consumer once we
  see real transient failures in the field.
- **OAuth credentials write-mode**: spec §13 left this as a plan-phase
  decision; the Dockerfile mounts `~/.claude` read-write to accommodate token
  rotation by the Claude Code CLI. If audit shows the CLI never writes, we
  can switch to `:ro`.
- **`aido rebuild-index` is a no-op stub** (Task 24): real reconciliation
  between the archive directory and `decisions` table is post-MVP.

---

## Self-review checklist (run after the last commit)

After all 35 tasks (0–34) are complete, walk through the spec one last time:

- [ ] Re-read each section of the spec; for every requirement, confirm a task
      implements it. If anything is uncovered, add a follow-up task.
- [ ] Run the full test suite: `pytest -v`. Expected: every test passes.
- [ ] Open `http://localhost:8765` in a browser, click through each tab.
- [ ] Run `tests/manual/runbook.md` end-to-end against the real Claude API.
- [ ] Commit a final tag: `git tag v0.1.0`.

---
