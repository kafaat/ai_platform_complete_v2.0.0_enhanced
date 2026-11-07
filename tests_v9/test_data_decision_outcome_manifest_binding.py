"""Bind the read-only proof manifest to actual repository paths in CI."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/ci/data_decision_outcome_proof_gate.py"
SPEC = importlib.util.spec_from_file_location("data_decision_outcome_manifest_gate", SCRIPT)
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def test_manifest_is_source_bound_but_cannot_certify_e3():
    manifest = json.loads((ROOT / "config/proof/data_decision_outcome_v1.json").read_text(encoding="utf-8"))
    report = GATE.validate(manifest, ROOT)
    assert report["manifest_valid"], report["errors"]
    assert len(report["stages"]) == len(GATE.EXPECTED_IDS) == 9
    assert report["source_review_only"] is True
    assert report["complete_e3"] is False
    with contextlib.redirect_stdout(io.StringIO()):
        rc = GATE.main(["--root", str(ROOT), "--require-e3"])
    assert rc == 2
