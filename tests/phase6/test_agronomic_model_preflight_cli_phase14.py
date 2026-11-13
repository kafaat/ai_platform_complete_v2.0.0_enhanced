from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "scripts/qa/agronomic_model_candidate_preflight.py"


def test_cli_cannot_grant_admission_to_self_declared_evidence(tmp_path):
    path = tmp_path / "input.json"
    path.write_text(
        json.dumps(
            {
                "evaluation": {},
                "promotion": {},
                "evidence": {"verified": True},
                "target_environment": "production",
            }
        )
    )
    p = subprocess.run(
        [sys.executable, str(CLI), "--input", str(path)],
        cwd=REPO,
        env={**os.environ, "PYTHONPATH": str(REPO)},
        capture_output=True,
        text=True,
    )
    assert p.returncode == 2
    reply = json.loads(p.stdout)
    assert reply["status"] == "SCHEMA_PREFLIGHT_ONLY_NOT_AUTHORIZED"
    assert reply["authorization_granted"] is False
    assert reply["activation_performed"] is False


def test_cli_rejects_invalid_json(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text("bogus{")
    p = subprocess.run(
        [sys.executable, str(CLI), "--input", str(path)],
        cwd=REPO,
        env={**os.environ, "PYTHONPATH": str(REPO)},
        capture_output=True,
        text=True,
    )
    assert p.returncode == 2 and "INPUT_INVALID" in p.stdout
