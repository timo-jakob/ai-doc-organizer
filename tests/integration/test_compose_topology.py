"""Topology assertions on docker-compose.yml — no docker required.

These parse the compose file as data and assert the deployment topology the C4
container diagram declares. They complement test_dockerfile.py (which actually
builds and runs the image behind a docker guard) by pinning the *shape* of the
compose stack cheaply and deterministically.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "docker-compose.yml"


def _services() -> dict:
    data = yaml.safe_load(COMPOSE.read_text())
    return data["services"]


def test_stack_has_aido_and_backup_services():
    services = _services()
    assert "aido" in services, "the primary aido service must exist"
    assert "aido-backup" in services, "the backup sidecar service must be declared"


def test_backup_sidecar_uses_stock_image_and_reads_data_readonly():
    backup = _services()["aido-backup"]
    assert backup["image"].startswith("offen/docker-volume-backup"), backup["image"]
    # Source data volume is mounted read-only; the /archive target is writable.
    ro_data = [v for v in backup["volumes"] if v.startswith("./data:") and v.endswith(":ro")]
    assert ro_data, f"backup must mount ./data read-only, got {backup['volumes']}"
    assert any("/archive" in v for v in backup["volumes"]), backup["volumes"]


def test_backup_sidecar_publishes_no_host_port():
    backup = _services()["aido-backup"]
    # An unattended ops sidecar exposes nothing to the host.
    assert "ports" not in backup, "backup sidecar must not publish any host port"


def test_primary_aido_service_still_serves_the_web_ui_port():
    # The sidecar addition must not disturb the primary service's host port.
    aido = _services()["aido"]
    assert any("8765" in p for p in aido.get("ports", [])), aido.get("ports")
