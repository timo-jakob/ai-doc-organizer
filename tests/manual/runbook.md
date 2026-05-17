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
