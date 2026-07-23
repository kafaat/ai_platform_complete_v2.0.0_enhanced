from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "config" / "evidence_lab_matrix.json"
COMPOSE = ROOT / "docker-compose.evidence-lab.yml"
RUNNER = ROOT / "scripts" / "certification" / "evidence_lab.py"


def test_claim_policy_never_replaces_live_certification() -> None:
    payload = json.loads(MATRIX.read_text(encoding="utf-8"))
    policy = payload["claim_policy"]
    assert policy["always_production_certified"] is False
    assert {
        "production_certified",
        "live_certified",
        "production_ready",
    }.issubset(set(policy["forbidden_claims"]))
    assert payload["capabilities"]
    assert all(row["remaining_live_gate"] for row in payload["capabilities"])


def test_compose_is_ephemeral_loopback_only_and_uses_postgres_16() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    assert "postgis/postgis:16-3.4" in compose
    assert "wiremock/wiremock:3.13.2" in compose
    assert "evidence-migrate:" in compose
    assert "./migrations:/migrations:ro" in compose
    assert "127.0.0.1:" in compose
    assert "0.0.0.0:" not in compose
    assert "tmpfs:" in compose
    assert "internal: true" in compose
    assert "no-new-privileges:true" in compose
    assert "docker-compose.v9.yml" not in compose


def test_static_contract_validation() -> None:
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--validate"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "SAHOOL_ENV": "evidence-lab"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "evidence_lab_contract_ok" in result.stdout


def test_runner_refuses_production_environment() -> None:
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--validate"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "SAHOOL_ENV": "production"},
    )
    assert result.returncode != 0
    assert "refuses this SAHOOL_ENV" in result.stdout + result.stderr
