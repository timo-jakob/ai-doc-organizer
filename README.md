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
