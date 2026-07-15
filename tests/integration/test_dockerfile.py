"""Smoke test: build the image, curl /healthz and the web UI pages inside the container."""

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
    # Pass host UID/GID so bind-mounted dirs are writable by the container
    # user (Dockerfile defaults match macOS but not Linux CI runners).
    tag = f"aido-test:{os.getpid()}"
    subprocess.run(
        [
            "docker",
            "build",
            "--build-arg",
            f"UID={os.getuid()}",
            "--build-arg",
            f"GID={os.getgid()}",
            "-t",
            tag,
            ".",
        ],
        cwd=REPO_ROOT,
        check=True,
    )

    # Prepare minimal mounts.
    data = tmp_path / "data"
    data.mkdir()
    logs = tmp_path / "logs"
    logs.mkdir()
    archive = tmp_path / "archive"
    archive.mkdir()
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        """
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
""".strip(),
        encoding="utf-8",
    )

    # Seed an _review category etc. by running aido init inside the container.
    seed = tmp_path / "seed.yaml"
    seed.write_text(
        """
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
""".strip(),
        encoding="utf-8",
    )

    init_args = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{cfg}:/app/config.yaml:ro",
        "-v",
        f"{data}:/data",
        "-v",
        f"{logs}:/var/log/aido",
        "-v",
        f"{archive}:/archive",
        "-v",
        f"{inbox}:/scans",
        "-v",
        f"{seed}:/tmp/seed.yaml:ro",
        tag,
        "python",
        "-m",
        "aido",
        "init",
        "--db",
        "/data/aido.sqlite",
        "--seed",
        "/tmp/seed.yaml",
    ]
    subprocess.run(init_args, check=True)

    # Launch container in background and curl /healthz on the mapped port.
    port = 18765
    name = f"aido-test-{os.getpid()}"
    run_args = [
        "docker",
        "run",
        "-d",
        "--name",
        name,
        "-p",
        f"127.0.0.1:{port}:8765",
        "-v",
        f"{cfg}:/app/config.yaml:ro",
        "-v",
        f"{data}:/data",
        "-v",
        f"{logs}:/var/log/aido",
        "-v",
        f"{archive}:/archive",
        "-v",
        f"{inbox}:/scans",
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

        # /healthz returns JSON without rendering a template, so a 200 there
        # says nothing about templates, static assets, or blueprint
        # registration (the missing-templates regression shipped through CI
        # exactly this way). Assert the web UI pages actually render: the
        # status must be exactly 200 (curl -f alone only fails on >= 400, so
        # a 3xx redirect would slip through) and the body must contain the
        # 'aido' brand string that base.html puts on every page.
        for page in ("/", "/needs-review", "/settings"):
            # One body file per page: curl -o does not truncate on an empty
            # body, so a shared file could serve the previous page's content
            # to the brand assertion.
            body_file = tmp_path / f"body-{page.strip('/') or 'index'}.html"
            r = subprocess.run(
                [
                    "curl",
                    "-sS",
                    "--max-time",
                    "15",
                    "-o",
                    str(body_file),
                    "-w",
                    "%{http_code}",
                    f"http://127.0.0.1:{port}{page}",
                ],
                capture_output=True,
            )
            assert r.returncode == 0, f"GET {page} failed: {r.stderr.decode(errors='replace')}"
            status = r.stdout.decode(errors="replace")
            assert status == "200", f"GET {page} returned HTTP {status}, expected 200"
            assert body_file.exists(), f"GET {page} returned 200 with an empty body"
            body = body_file.read_bytes()
            assert b"aido" in body, f"GET {page} rendered without the 'aido' brand string"
    finally:
        subprocess.run(["docker", "rm", "-f", name], check=False)
        subprocess.run(["docker", "image", "rm", tag], check=False)
