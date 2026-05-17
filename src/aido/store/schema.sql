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
