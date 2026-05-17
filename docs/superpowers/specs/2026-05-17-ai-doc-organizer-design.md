# ai-doc-organizer — Design Spec

**Date:** 2026-05-17
**Codename:** `aido`
**Status:** Approved for v1 implementation

## 1. Purpose

`aido` watches a scanner inbox folder on a Synology NAS, classifies each incoming PDF using Claude, and files it into a per-person / per-category archive with a structured filename. The user reviews and corrects decisions retrospectively in a LAN-accessible web UI. The system serves a 4-person household sharing one scanner.

### 1.1 Goals (v1)

- Hands-off filing of single-document PDFs for the common cases (invoices, bills, contracts, medical letters).
- Per-person organization with a "shared" bucket for genuinely joint documents.
- Confidence-aware routing: uncertain or new-category cases land in a `_review/` bucket; nothing is silently lost.
- Retrospective audit and correction via web UI; corrections are recorded.
- Stable filing convention so the archive remains usable without the tool.
- Runs on Synology DS214+ with Python 3.9, no Docker.
- Classifier behind an interface so a future local-LLM backend can drop in.

### 1.2 Non-goals (v1)

OCR fallback for image-only PDFs; multi-document PDF splitting; auth on the web UI; per-user UI views; local LLM implementation; notifications; counterparty normalization; malware scanning; backup of the archive.

---

## 2. Architecture

```
                  ┌─────────────────────────────────────────────┐
                  │              aido daemon (Python)           │
                  │                                             │
   scanner SMB    │   ┌──────────┐   ┌──────────┐               │
   ───────────►   │   │ watcher  │──►│  worker  │──┐            │
   ~/Scans/in     │   │(watchdog)│   │ pipeline │  │            │
                  │   └──────────┘   └─────┬────┘  │            │
                  │                        │       ▼            │
                  │                        ▼  ┌──────────┐      │
                  │                  ┌──────────┐ │ filing │    │
                  │                  │classifier│ │executor│    │
                  │                  │interface │ └────┬───┘    │
                  │                  └─────┬────┘      │        │
                  │                        │           │        │
                  │                        ▼           ▼        │
                  │                ┌──────────────┐  ~/Archive  │
                  │                │ ClaudeAPI    │             │
                  │                │ classifier   │             │
                  │                └──────────────┘             │
                  │                                             │
                  │   ┌────────────────────────────────────┐    │
                  │   │   SQLite (audit log, taxonomy)     │    │
                  │   └────────────────────────────────────┘    │
                  │                  ▲                          │
                  │            ┌──────────┐                     │
                  │            │  web UI  │ ◄── LAN browser     │
                  │            │ (Flask)  │      :8765          │
                  │            └──────────┘                     │
                  └─────────────────────────────────────────────┘
```

### 2.1 Modules

| Module | Responsibility |
|--------|----------------|
| `watcher` | `watchdog` inotify on the scan inbox; enqueues new PDFs. |
| `worker` | Stabilize/dedupe → extract text → classify → file → record decision. Single background thread; one doc at a time. |
| `classifier` | `Classifier` Protocol + `ClaudeAPIClassifier` implementation. The future swap point. |
| `filing_executor` | Atomic move into archive, filename collision handling. |
| `store` | Thin repository over SQLite. No ORM. |
| `webui` | Flask app for the retro-audit panel; calls back into the daemon's internal mutation endpoint for any write. |
| `config` | `config.yaml` for runtime knobs; the DB is the source of truth for taxonomy. |

### 2.2 Process topology

A single Python process hosts watcher, worker pipeline, and the Flask web UI together. Started via Synology Task Scheduler on boot; clean shutdown on system shutdown via SIGTERM. Pidfile at `/volume1/aido/run/aido.pid` prevents double-starts.

---

## 3. Folder layout and filename convention

### 3.1 Archive layout

```
Archive/                                     # archive_root, configurable
├── timo/
│   ├── rechnungen/
│   ├── steuer/
│   ├── medizin/
│   └── vertraege/
├── anna/
├── child1/
├── child2/
├── shared/                          ← family / joint documents
│   ├── nebenkosten/
│   └── vertraege/
└── _review/                         ← classifier flagged for audit
```

- Category names are German (per user preference). The same category list is applied uniformly under every person.
- The `shared/` bucket holds documents whose addressee is the household at large; documents addressed to a single named family member always go to that person, even when other family members are also addressed.
- `_review/` is a single bucket (no per-person sub-folders) holding any document that was not auto-filed.

### 3.2 Filename convention

```
YYYY-MM-DD_<doctype>_<counterparty>.pdf
```

- Date is extracted from document content (invoice date, letter date). If extraction fails, scan date is used and the audit row is flagged.
- Doctype is a slug from a controlled vocabulary (`rechnung`, `steuerbescheid`, `kontoauszug`, …). Fallback: `letter`.
- Counterparty is the sender/issuer, ASCII-normalized (umlauts transliterated `ä→ae`, `ö→oe`, `ü→ue`, `ß→ss`; spaces → `-`). Fallback: `unknown`.
- Length cap: ~80 characters; trailing parts truncated if needed.
- Collision: append `_2`, `_3`, … before the `.pdf` suffix.

---

## 4. Classification pipeline

Per document, single-threaded:

1. **Stabilize** — wait until file size has been stable for 2s (avoid reading half-written files).
2. **Dedupe** — SHA-256 of the file; skip if `source_hash` already in `decisions`. Logged as `duplicate_skip`.
3. **Extract text** — `pypdf` reads the embedded text layer. Empty result → route to `_review/` with reason `no_extractable_text`.
4. **Build prompt** — system prompt is the taxonomy rendered from the DB (persons + aliases, categories, doctypes, filename rules, output schema). User prompt is the document text (truncated to ~6 KB) plus the original filename as a weak hint.
5. **Classify** — call `Classifier.classify()` → `ClassificationResult`.
6. **Resolve slugs** — map `person_slug` → `person_id`, `category_slug` → `category_id`, `doctype_slug` → `doctype_id`. Unknown slug → route to `_review/`.
7. **Route** — if `overall_confidence ≥ threshold` AND a `new_category_proposal` is not set → file under `<archive>/<person>/<category>/<filename>.pdf`. Otherwise → file under `_review/<filename>.pdf`.
8. **Move atomically** and insert a `decisions` row.

### 4.1 Classifier interface

```python
# aido.classifier.base
from typing import Protocol, Optional
from dataclasses import dataclass

@dataclass
class ClassificationResult:
    person_slug: str
    category_slug: str
    doctype_slug: str
    document_date: str            # 'YYYY-MM-DD'
    counterparty: str
    proposed_filename: str
    overall_confidence: float
    person_confidence: float
    category_confidence: float
    new_category_proposal: Optional[str]
    reasoning: str

class Classifier(Protocol):
    def classify(self, text: str, original_filename: str) -> ClassificationResult: ...
```

Concrete implementations:

- `ClaudeAPIClassifier` — v1; uses the `anthropic` Python SDK with an API key from `.env`. Default model `claude-opus-4-7`; configurable.
- `LocalLLMClassifier` — Mac mini phase (later); same Protocol.
- `AgentSDKClassifier` — possibly later (Max Plan via OAuth); requires Python 3.10+, so blocked on Mac mini migration.

### 4.2 Prompt strategy

- The system prompt (taxonomy + rules + output schema) is identical across calls so Anthropic's prompt cache applies — after the first call, the system portion is ~90% cheaper.
- Output requested via tool-use schema for strict typing; the model returns a structured `ClassificationResult` payload.
- The joint-mail rule is in the prompt: *"If the addressee names a single family member, file under that person. Use shared only when no individual family member is identifiable."*

### 4.3 Confidence threshold

`classifier.review_confidence_threshold` in `config.yaml`, default `0.75`. Documents with `overall_confidence` below the threshold or with `new_category_proposal` set are routed to `_review/`.

---

## 5. Web UI: retro-audit panel

A single Flask process running inside the daemon, binding to `0.0.0.0:8765` (configurable). LAN-only; no auth, per the user's choice for a trusted home network.

### 5.1 Layout

Two-pane:

- **Left** — a feed of decisions, most recent first, with a confidence chip per row and a `_review` badge for uncertain entries. Three tabs: *Recently filed*, *Needs review (N)* (default landing when N > 0), *All*. A *Settings* tab exposes persons, categories, doctypes, aliases.
- **Right** — detail for the selected document: PDF preview (first page), current location, original location, the classifier's reasoning, and an inline form to re-file (person dropdown, category dropdown, filename input).

### 5.2 Mutations

The web UI never writes the DB or `config.yaml` directly. Each user action goes through the daemon's mutation API (single-writer model); the daemon performs the action and inserts a `manual_actions` row. The transport — in-process function call vs. internal HTTP — is an implementation choice; see §13. Supported actions: `re_file`, `rename`, `delete`, `approve` (accept the classifier's decision as-is), `promote_category` (turn a `new_category_proposal` into a real category and re-file).

### 5.3 Rendering

Server-rendered HTML (Jinja2 templates) with vanilla JavaScript for inline form behavior. No SPA framework. Keeps the DS214+ footprint small and the page weight low.

---

## 6. State: SQLite schema

`detect_types=PARSE_DECLTYPES | PARSE_COLNAMES` so `DATE` / `TIMESTAMP` columns round-trip as `datetime.date` / `datetime.datetime`. `PRAGMA foreign_keys = ON` on every connection. `PRAGMA journal_mode = WAL` for crash safety. STRICT tables are not used (DSM ships SQLite < 3.37); typing is enforced via `CHECK` constraints and Python-side enums.

### 6.1 Lookup tables

```sql
CREATE TABLE persons (
  id           INTEGER PRIMARY KEY,
  slug         TEXT    NOT NULL UNIQUE,            -- 'timo', 'anna', 'shared', ...
  display_name TEXT    NOT NULL,
  is_shared    INTEGER NOT NULL DEFAULT 0 CHECK (is_shared IN (0, 1)),
  is_active    INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE person_aliases (
  id               INTEGER PRIMARY KEY,
  person_id        INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
  alias            TEXT    NOT NULL,               -- 'Jakob', 'Jacob', 'Penélope'
  alias_normalized TEXT    NOT NULL UNIQUE         -- 'jakob', 'penelope'
);
CREATE INDEX idx_aliases_normalized ON person_aliases(alias_normalized);

CREATE TABLE categories (
  id           INTEGER PRIMARY KEY,
  slug         TEXT    NOT NULL UNIQUE,
  display_name TEXT    NOT NULL,
  description  TEXT,                                -- one-line, used in AI prompt
  is_review    INTEGER NOT NULL DEFAULT 0 CHECK (is_review IN (0, 1)),
  is_active    INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE doctypes (
  id           INTEGER PRIMARY KEY,
  slug         TEXT    NOT NULL UNIQUE,
  display_name TEXT    NOT NULL,
  description  TEXT,
  is_active    INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);
```

### 6.2 Fact tables

```sql
CREATE TABLE decisions (
  id                    INTEGER   PRIMARY KEY,
  created_at            TIMESTAMP NOT NULL,
  source_hash           TEXT      NOT NULL UNIQUE,
  source_path           TEXT      NOT NULL,
  filed_path            TEXT      NOT NULL,

  person_id             INTEGER   NOT NULL REFERENCES persons(id),
  category_id           INTEGER   NOT NULL REFERENCES categories(id),
  doctype_id            INTEGER            REFERENCES doctypes(id),  -- NULL when _review with no doctype

  document_date         DATE,
  counterparty          TEXT,
  proposed_filename     TEXT      NOT NULL,

  overall_confidence    REAL      NOT NULL CHECK (overall_confidence  BETWEEN 0 AND 1),
  person_confidence     REAL      NOT NULL CHECK (person_confidence   BETWEEN 0 AND 1),
  category_confidence   REAL      NOT NULL CHECK (category_confidence BETWEEN 0 AND 1),

  reasoning             TEXT,
  classifier_model      TEXT      NOT NULL,
  new_category_proposal TEXT,

  needs_review          INTEGER   NOT NULL CHECK (needs_review IN (0, 1)),
  status                TEXT      NOT NULL CHECK (status IN
                            ('auto_filed', 'review', 'human_filed', 'failed'))
);
CREATE INDEX idx_decisions_created ON decisions(created_at);
CREATE INDEX idx_decisions_status  ON decisions(status);
CREATE INDEX idx_decisions_person  ON decisions(person_id);

CREATE TABLE manual_actions (
  id                  INTEGER   PRIMARY KEY,
  decision_id         INTEGER   NOT NULL REFERENCES decisions(id),
  action              TEXT      NOT NULL CHECK (action IN
                          ('re_file', 'rename', 'delete', 'approve', 'promote_category')),
  before_path         TEXT      NOT NULL,
  after_path          TEXT,
  before_person_id    INTEGER            REFERENCES persons(id),
  after_person_id     INTEGER            REFERENCES persons(id),
  before_category_id  INTEGER            REFERENCES categories(id),
  after_category_id   INTEGER            REFERENCES categories(id),
  created_at          TIMESTAMP NOT NULL,
  note                TEXT
);

CREATE TABLE pending_jobs (
  id              INTEGER   PRIMARY KEY,
  source_path     TEXT      NOT NULL,
  source_hash     TEXT      NOT NULL UNIQUE,
  attempts        INTEGER   NOT NULL DEFAULT 0,
  next_attempt_at TIMESTAMP NOT NULL,
  last_error      TEXT,
  created_at      TIMESTAMP NOT NULL
);
```

### 6.3 Python-side types

```python
from enum import Enum

class DecisionStatus(str, Enum):
    AUTO_FILED  = 'auto_filed'
    REVIEW      = 'review'
    HUMAN_FILED = 'human_filed'
    FAILED      = 'failed'

class ManualAction(str, Enum):
    RE_FILE          = 're_file'
    RENAME           = 'rename'
    DELETE           = 'delete'
    APPROVE          = 'approve'
    PROMOTE_CATEGORY = 'promote_category'
```

CHECK constraints on the DB side + str-mixin enums in Python give belt-and-suspenders without runtime overhead.

---

## 7. Configuration

```yaml
# config.yaml
archive_root: /volume1/homes/timo/Documents/Archive
scan_inbox:   /volume1/scans/incoming
db_path:      /volume1/aido/data/aido.sqlite
log_path:     /volume1/aido/logs/aido.log

classifier:
  backend: claude_api
  model:   claude-opus-4-7
  review_confidence_threshold: 0.75

web:
  bind: 0.0.0.0
  port: 8765
```

- `.env` next to `config.yaml` holds `ANTHROPIC_API_KEY` (chmod 600).
- Taxonomy (persons, aliases, categories, doctypes) lives in the DB, **not** in `config.yaml`. The DB is the source of truth.
- `config.yaml` is read at daemon startup and on SIGHUP. Mutations to runtime config are rare; the file is edited by hand.
- The daemon owns the only writer for `config.yaml` mutations (currently none from the UI, but the writer pattern uses `ruamel.yaml` for round-trip-safe edits if that changes).

### 7.1 Bootstrap

A one-shot `aido init` CLI seeds the DB from interactive prompts:
- Asks for the 4 family members (display name, slug, initial aliases) and creates a `shared` row.
- Loads a starter category list (`rechnungen`, `steuer`, `medizin`, `vertraege`, `bank`, `versicherung`, `nebenkosten`, `briefe`, `schule`) and a starter doctype list.
- Creates the archive root and `_review/` if missing.
- Writes a default `config.yaml` if not present.

---

## 8. Synology deployment

### 8.1 Filesystem

```
/volume1/aido/
├── venv/                        # Python 3.9 virtualenv
├── src/aido/...                 # the package
├── config.yaml
├── .env                         # chmod 600
├── data/
│   └── aido.sqlite
├── logs/
│   └── aido.log
└── run/
    └── aido.pid

/volume1/scans/incoming/         # scanner SMB share, watched
/volume1/homes/<user>/Documents/Archive/   # archive_root (or shared volume)
```

### 8.2 Process lifecycle

- **Start on boot**: Synology Task Scheduler → Triggered Task → Boot-up → runs `/volume1/aido/venv/bin/python -m aido.daemon`.
- **Stop on shutdown**: Triggered Task → Shutdown → sends SIGTERM to the pidfile and waits up to 30s.
- **Manual control**: `aido start | stop | status | restart` CLI wraps the same.
- **Daemon refuses to start** if a live process is already running (pidfile check + PID liveness probe).
- **`GET /healthz`** returns daemon status (`ok` / `auth_failed` / `cannot_write` / `degraded`), last classification timestamp, pending_jobs count, `_review` count.

### 8.3 Dependencies (lean, all pure-Python or ARM-compatible wheels)

- `anthropic` (Python SDK; pure Python)
- `pypdf` (PDF text extraction; pure Python)
- `watchdog` (inotify file watching)
- `flask` (web UI)
- `jinja2` (templates; transitive)
- `ruamel.yaml` (round-trip YAML, for future config mutations)
- `pytest` (dev only)

No torch / transformers / heavy ML libs.

---

## 9. Error handling

| Failure mode | Reaction |
|--------------|----------|
| PDF unreadable / encrypted | Route to `_review/`; `reason='pdf_unreadable'`; `status='review'`. |
| PDF has no text layer | Route to `_review/`; `reason='no_extractable_text'`. OCR is v2. |
| Anthropic transient (5xx, network) | Add to `pending_jobs`; backoff 1s / 5s / 30s / 5min / 1hr. After 5 attempts → `_review/` with last error preserved. |
| Anthropic 429 (rate limit) | Respect `Retry-After`; else backoff. |
| Anthropic 401 (auth) | Log at ERROR; halt classification; daemon stays alive; `/healthz` reports `auth_failed`. |
| AI output fails schema validation | One retry with stricter prompt; then `_review/` with `reason='invalid_classification'`. |
| AI returns unknown slug | Route to `_review/`; audit captures the raw slug. |
| Filename collision | Append `_2`, `_3`, … atomically. |
| Permission denied / disk full | `status='failed'`; file stays in inbox; `/healthz` reports `cannot_write`. |
| Daemon crashes mid-classification | Pidfile prevents double-start. On startup: reconcile inbox vs decisions by hash; resume `pending_jobs`. |
| Duplicate scan | `UNIQUE(source_hash)` blocks; logged `duplicate_skip`; file removed from inbox. |
| Daemon ↔ UI write race | Web UI calls daemon's internal mutation endpoint; daemon is the sole writer. |

---

## 10. Logging and observability

- **Structured JSON logs** (one event per line) to `logs/aido.log`. Rotated weekly via `RotatingFileHandler`, keep 8 weeks.
- **Classification log entry** records: `source_hash`, decision id, model, latency, token counts (input/output/cached), estimated cost, confidences.
- **`GET /healthz`** as in §8.2.
- **Stats panel** in the web UI: docs/day, docs/week, `_review` depth, average confidence, rolling 30-day API spend (computed from logged token counts × published prices).

---

## 11. Testing strategy

- **pytest** as the runner. Network-free by default.
- **Unit tests** for:
  - Filename builder (umlaut transliteration, ASCII normalisation, length cap, collision suffix).
  - Alias normalisation (`"Penélope"` → `"penelope"`).
  - `pypdf` text extractor with fixture PDFs (text-layer present, image-only, encrypted, empty).
  - `store` repository against in-memory SQLite (asserts on row shape + CHECK constraint behaviour).
  - Classifier slug resolution and route decision given a canned AI response.
- **Integration tests**: a `FakeClassifier` returning scripted results. Drop a fixture PDF in a temp inbox, run one worker tick, assert file moved + `decisions` row correct + audit row inserted when the web UI re-files.
- **Web UI**: Flask test client; assert routes return expected HTML/JSON and that mutations land in the DB.
- **Smoke checklist on the NAS**: `docs/runbook.md` — start daemon, drop sample PDFs (DE invoice, EN invoice, image-only PDF, multi-addressee letter) on the SMB share, open the web UI on a phone, re-file one document, restart the daemon, verify state persists.
- **No load testing** for v1 — volume is light/moderate.
- **Fixture PDFs**: `tests/fixtures/` with at least one DE invoice, one EN invoice, one image-only PDF, one with no addressee. Real-but-anonymised content.

---

## 12. Out of scope for v1

Deferred to post-MVP iterations driven by family-member feedback:

- OCR fallback for image-only PDFs (Mac-mini phase).
- Multi-document PDF splitting.
- Authentication on the web UI.
- Per-user filtered views in the web UI.
- Local LLM classifier implementation (Mac-mini phase).
- Notifications (email / push) on uncertain docs.
- Counterparty normalisation into its own table.
- Mobile-optimised UI polish beyond basic responsive layout.
- Malware / anti-virus scanning of incoming PDFs.
- Archive backup (delegated to Synology's native backup tooling).

---

## 13. Open implementation questions (for the plan phase, not blocking)

These don't change the design but are decisions the implementation plan must make:

1. **PDF preview rendering in the web UI**: render the first page server-side (e.g., a thumbnail via `pypdf` + `pillow`) or embed via `<embed>` / `<iframe>` and let the browser handle it. The latter is simpler but heavier on the LAN.
2. **Web UI internal mutation endpoint**: shared in-process function call vs. internal HTTP. The single-process design allows either; in-process is simpler.
3. **`aido init` interactivity**: pure CLI prompts vs. seed from a starter YAML file. Either works; CLI prompts are friendlier for the user but harder to test.

These are sized to be answered while writing the implementation plan.

---

## 14. Decision log (from brainstorming)

| Decision | Choice |
|----------|--------|
| Core job | Auto-file scanned documents into folders. |
| Input source | Watched scanner inbox folder; PDFs with embedded OCR text only. |
| Taxonomy model | Hybrid: fixed list per the DB; AI may propose new categories which become a one-click UI action. |
| Review mode | Auto-file everything (no upfront gate); retrospective audit in the web UI. |
| Folder layout | `<archive>/<person>/<category>/<file>`, German category names, shared list applied uniformly under every person. |
| People | 4 family members + `shared/` bucket. |
| Person ID | AI extracts addressee → matches against persons/aliases in DB. Joint mail with a single named addressee goes to that person; shared is the fallback. |
| AI backend | Pluggable via `Classifier` Protocol. v1: Claude API (Opus 4.7) via `anthropic` Python SDK + API key. Future: local LLM (Mac mini), Agent SDK + Max Plan (Python 3.10+, post-Synology). |
| Stack | Python 3.9 on Synology DS214+, no Docker. |
| Languages handled | German (primary), English, Spanish, French, Italian, Dutch. |
| Volume | Light / moderate; will grow as family adopts. |
| Process topology | Single daemon, SQLite for state. |
| Web UI | LAN-bound Flask on `:8765`, no auth, server-rendered HTML. |
| Rollout | MVP-first; collect feedback from each family member before adding features. |
