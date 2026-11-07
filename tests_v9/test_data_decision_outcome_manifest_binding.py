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


def test_meta_proof_files_are_excluded_from_capability_scanner():
    scanner_script = ROOT / "scripts/ci/capability_mapping_engine.py"
    scanner_spec = importlib.util.spec_from_file_location("capability_mapping_proof_exclusion", scanner_script)
    assert scanner_spec and scanner_spec.loader
    scanner = importlib.util.module_from_spec(scanner_spec)
    scanner_spec.loader.exec_module(scanner)
    expected = {
        "config/proof/data_decision_outcome_v1.json",
        "docs/strategy/DATA_DECISION_OUTCOME_PROOF_20261107.md",
        "scripts/ci/data_decision_outcome_proof_gate.py",
        "tests_v9/test_data_decision_outcome_manifest_binding.py",
        "tests_v9/test_data_decision_outcome_proof_gate.py",
    }
    assert expected <= scanner.META_GOVERNANCE_FILES
    scanned = {p.relative_to(scanner.ROOT).as_posix() for p in scanner.iter_files()}
    assert expected.isdisjoint(scanned)
