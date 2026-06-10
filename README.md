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

## Troubleshooting

On startup the daemon runs pre-flight checks and exits with code 78
(`EX_CONFIG`) and a one-line `aido: config error: ...` message on stderr if it
detects a known misconfiguration. Check `docker compose logs aido` for one of:

| Message | Cause / fix |
|---------|-------------|
| `... is a directory, not a file — Docker creates an empty directory when the bind-mount source is missing; create the config file on the host and restart` | `config.yaml` was missing on the host when the container started, so Docker created an empty directory in its place. Remove the directory, run `cp config.example.yaml config.yaml`, and restart. |
| `classifier.backend is 'anthropic_api' but ANTHROPIC_API_KEY is unset or blank — set it in the container environment` | Add `ANTHROPIC_API_KEY=sk-ant-...` to the project `.env` file (or your shell environment) and restart. |
| `archive_root ... is not writable — check that the directory exists and the bind mount allows writes` | The archive directory is missing on the host or mounted read-only. Create it and check the volume entry in `docker-compose.yml`. |
| `scan_inbox ... does not exist or is not readable — check the scanner share bind mount` | The scanner inbox folder is missing or unreadable. Create it (e.g. `~/Scans/incoming/`) and check the volume entry in `docker-compose.yml`. |
| `db_path parent directory ... is not writable — the daemon cannot create or open its SQLite database there` | The data directory is missing on the host or mounted read-only. Create it and check the volume entry in `docker-compose.yml`. |

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
