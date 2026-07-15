# Use the CLI

How to work with ai-doc-organizer from the command line.

!!! note "Seeded page"
    This page was seeded because the project exposes a command-line
    interface. Grow it alongside the features: each user-visible CLI change
    should update this guide (or add a sibling how-to page) in the same PR.

## Run a command

Show the most common invocation and its output.

## Get help

Every command documents itself:

```console
$ <command> --help
```

## Common tasks

Document each recurring job as its own section — the exact command, the
expected output, and how to interpret it.

### Reconcile the index after manual archive changes

`aido rebuild-index` walks the archive tree and brings the decisions index
back in line with what is actually on disk — useful after you moved or
deleted files by hand, cleaned up `_review/`, or mirrored an existing
archive onto a fresh Mac mini with rsync. It never moves, renames, or
re-classifies anything; it only reconciles existence.

```console
$ aido rebuild-index --db /data/aido.sqlite --archive-root /archive
2 added, 1 flagged, 148 in sync
```

- **added** — PDFs found on disk that had no index entry, e.g. a
  `timo/rechnungen/2026-03-12_stadtwerke-muenchen_rechnung.pdf` you filed
  by hand. Each gets an entry marked as human-filed, with the person and
  category read from its `<person>/<category>/` folder (files that don't
  match that layout land under the shared person in `_review`).
- **flagged** — index entries whose file no longer exists, e.g. a
  `shared/vertraege/2025-11-02_telekom_vertrag.pdf` you deleted. These are
  marked failed so they stop showing up as filed documents.
- **in sync** — entries whose file is exactly where the index says.

A document you *moved* within the archive keeps its single index entry —
the entry is re-pointed to the new location rather than counted as added
plus flagged. An entry that was flagged failed earlier whose file is back
(restored from backup, remounted) is recovered automatically. A file the
command cannot read is skipped with a warning instead of aborting the run.

**Safety guard:** if more than half of all indexed documents would be
flagged as missing, the command assumes the archive is mis-mounted or
half-synced (an empty USB mount, an unfinished rsync), aborts with an
error, and changes nothing. Fix the mount and re-run. The whole reconcile
is one transaction: on any error the index is left exactly as it was.
