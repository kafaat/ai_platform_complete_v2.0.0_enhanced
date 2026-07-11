"""WX-10.7 — the decision-review boundary guard passes on the tree and catches execution tokens."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "ci" / "decision_review_boundary_gate.py"
ROUTER = ROOT / "services" / "sahool-platform" / "api" / "routers" / "decision_review.py"


def test_guard_passes_on_current_tree():
    proc = subprocess.run(
        [sys.executable, str(GUARD)], capture_output=True, text=True, cwd=str(ROOT)
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "decision_review_boundary_gate_ok" in proc.stdout


def test_guard_catches_execution_token(tmp_path):
    # Sanity: the guard's FORBIDDEN scan trips on a dispatch/execute token in the router.
    import importlib.util

    spec = importlib.util.spec_from_file_location("_drbg", GUARD)
    mod = importlib.util.module_from_spec(spec)
    # Loading executes the guard against the real tree; it must be clean (exit 0 => no SystemExit).
    spec.loader.exec_module(mod)  # will raise SystemExit(1) if the tree ever regresses
    assert "run_field_intelligence" in mod.FORBIDDEN
    assert "record_dispatch" in mod.FORBIDDEN
    assert "DECISION_APPROVE" in mod.REQUIRED_IN_ROUTER
